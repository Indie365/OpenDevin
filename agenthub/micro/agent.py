import json
from typing import Dict, List

from jinja2 import BaseLoader, Environment

from opendevin.controller.agent import Agent
from opendevin.controller.state.state import State
from opendevin.core.exceptions import LLMOutputError
from opendevin.events.action import (
    Action,
    AgentFinishAction,
    AgentRejectAction,
    action_from_dict,
)
from opendevin.events.observation import CmdOutputObservation, Observation
from opendevin.llm.llm import LLM

from .instructions import instructions
from .registry import all_microagents


def parse_response(orig_response: str) -> Action:
    depth = 0
    start = -1
    for i, char in enumerate(orig_response):
        if char == '{':
            if depth == 0:
                start = i
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0 and start != -1:
                response = orig_response[start : i + 1]
                try:
                    action_dict = json.loads(response)
                    action = action_from_dict(action_dict)
                    return action
                except json.JSONDecodeError as e:
                    raise LLMOutputError(
                        'Invalid JSON in response. Please make sure the response is a valid JSON object.'
                    ) from e
    raise LLMOutputError('No valid JSON object found in response.')


def my_encoder(obj):
    """
    Encodes objects as dictionaries

    Parameters:
    - obj (Object): An object that will be converted

    Returns:
    - dict: If the object can be converted it is returned in dict format
    """
    if hasattr(obj, 'to_dict'):
        return obj.to_dict()


def to_json(obj, **kwargs):
    """
    Serialize an object to str format
    """
    return json.dumps(obj, default=my_encoder, **kwargs)


class MicroAgent(Agent):
    prompt = ''
    agent_definition: Dict = {}

    def __init__(self, llm: LLM):
        super().__init__(llm)
        if 'name' not in self.agent_definition:
            raise ValueError('Agent definition must contain a name')
        self.delegates = all_microagents.copy()
        del self.delegates[self.agent_definition['name']]
        self.workflow_step = 0
        self.workflow_data: dict = {}

    def prompt_to_action(self, prompt: str, state: State, inputs: dict = {}) -> Action:
        template = Environment(loader=BaseLoader).from_string(prompt)
        rendered = template.render(
            state=state,
            instructions=instructions,
            to_json=to_json,
            delegates=self.delegates,
            inputs=inputs,
        )
        messages = [{'content': rendered, 'role': 'user'}]
        resp = self.llm.completion(messages=messages)
        action_resp = resp['choices'][0]['message']['content']
        state.num_of_chars += len(prompt) + len(action_resp)
        action = parse_response(action_resp)
        return action

    def step(self, state: State) -> Action:
        if 'workflow' in self.agent_definition:
            return self.step_workflow(state)
        return self.prompt_to_action(self.prompt, state)

    def step_workflow(self, state: State) -> Action:
        if self.workflow_step >= len(self.agent_definition['workflow']):
            return AgentFinishAction()
        if self.workflow_step > 0:
            if not self.update_previous_workflow_step(state):
                return AgentRejectAction()

        step = self.agent_definition['workflow'][self.workflow_step]
        self.workflow_step += 1
        do = step.get('do', {})
        if 'action' in do:
            action = action_from_dict(do)
            return action
        elif 'prompt' in do:
            prompt = do['prompt']
            inputs = do.get('inputs', {})
            # TODO: template out
            return self.prompt_to_action(prompt, state, inputs)
        else:
            raise ValueError('Step must contain either an action or a prompt')

    def update_previous_workflow_step(self, state: State) -> bool:
        prev_step = self.agent_definition['workflow'][self.workflow_step - 1]
        for action, obs in state.updated_info:
            if (
                'action' in prev_step['do']
                and action.action == prev_step['do']['action']  # type: ignore [attr-defined]
            ):
                self.workflow_data[prev_step['name']] = obs
                if not self.validate_observation(action, obs):
                    return False
        return True

    def validate_observation(self, action: Action, obs: Observation) -> bool:
        if isinstance(obs, CmdOutputObservation):
            return obs.exit_code == 0
        return True

    def search_memory(self, query: str) -> List[str]:
        return []
