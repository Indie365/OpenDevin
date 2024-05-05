import argparse
import logging
import os
import pathlib
import platform
from dataclasses import dataclass, field, fields
from types import UnionType
from typing import Any, ClassVar, get_args, get_origin

import toml
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()


class Singleton(type):
    _instances: dict = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        else:
            # allow updates, just update existing instance
            # perhaps not the most orthodox way to do it, though it simplifies client code
            # useful for pre-defined groups of settings
            instance = cls._instances[cls]
            for key, value in kwargs.items():
                setattr(instance, key, value)
        return cls._instances[cls]


@dataclass
class LLMConfig(metaclass=Singleton):
    model: str = 'gpt-3.5-turbo-1106'
    api_key: str | None = None
    base_url: str | None = None
    api_version: str | None = None
    embedding_model: str = 'local'
    embedding_base_url: str | None = None
    embedding_deployment_name: str | None = None
    num_retries: int = 5
    retry_min_wait: int = 3
    retry_max_wait: int = 60
    timeout: int | None = None
    max_return_tokens: int | None = None
    max_chars: int = 5_000_000  # fallback for token counting
    temperature: float = 0
    top_p: float = 0.5

    def defaults_to_dict(self) -> dict:
        """
        Serialize fields to a dict for the frontend, including type hints, defaults, and whether it's optional.
        """
        dict = {}
        for f in fields(self):
            dict[f.name] = get_field_info(f)
        return dict


@dataclass
class AgentConfig(metaclass=Singleton):
    name: str = 'CodeActAgent'
    memory_enabled: bool = False
    memory_max_threads: int = 2

    def defaults_to_dict(self) -> dict:
        """
        Serialize fields to a dict for the frontend, including type hints, defaults, and whether it's optional.
        """
        dict = {}
        for f in fields(self):
            dict[f.name] = get_field_info(f)
        return dict


@dataclass
class AppConfig(metaclass=Singleton):
    llm: LLMConfig = field(default_factory=LLMConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    workspace_base: str = os.getcwd()
    workspace_mount_path: str = os.getcwd()
    workspace_mount_path_in_sandbox: str = '/workspace'
    workspace_mount_rewrite: str | None = None
    cache_dir: str = '/tmp/cache'
    sandbox_container_image: str = 'ghcr.io/opendevin/sandbox' + (
        f':{os.getenv("OPEN_DEVIN_BUILD_VERSION")}'
        if os.getenv('OPEN_DEVIN_BUILD_VERSION')
        else ':main'
    )
    run_as_devin: bool = True
    max_iterations: int = 100
    e2b_api_key: str = ''
    sandbox_type: str = 'ssh'  # Can be 'ssh', 'exec', or 'e2b'
    use_host_network: bool = False
    ssh_hostname: str = 'localhost'
    disable_color: bool = False
    sandbox_user_id: int = os.getuid() if hasattr(os, 'getuid') else 1000
    sandbox_timeout: int = 120
    github_token: str | None = None

    defaults_dict: ClassVar[dict] = {}

    def __post_init__(self):
        """
        Post-initialization hook, called when the instance is created with only default values.
        """
        AppConfig.defaults_dict = self.defaults_to_dict()

    def defaults_to_dict(self) -> dict:
        """
        Serialize fields to a dict for the frontend, including type hints, defaults, and whether it's optional.
        """
        dict = {}
        for f in fields(self):
            field_value = getattr(self, f.name)
            if isinstance(field_value, (LLMConfig, AgentConfig)):
                dict[f.name] = field_value.defaults_to_dict()
            else:
                dict[f.name] = get_field_info(f)
        return dict


def get_field_info(field):
    """
    Extract information about a dataclass field: type, optional, and default.

    Args:
        field: The field to extract information from.

    Returns: A dict with the field's type, whether it's optional, and its default value.
    """
    field_type = field.type
    optional = False

    # for types like str | None, find the non-None type and set optional to True
    if get_origin(field_type) is UnionType:
        types = get_args(field_type)
        non_none_arg = next((t for t in types if t is not type(None)), None)
        if non_none_arg is not None:
            field_type = non_none_arg
            optional = True

    # type name in a pretty format
    type_name = (
        field_type.__name__ if hasattr(field_type, '__name__') else str(field_type)
    )

    # default is always present
    default = field.default

    # return a schema with the useful info for the frontend
    return {'type': type_name.lower(), 'optional': optional, 'default': default}


def load_from_env(config: AppConfig, env_or_toml_dict: dict | os._Environ):
    """Reads the env-style vars and sets config attributes based on env vars or a config.toml dict.
    Compatibility with vars like LLM_BASE_URL, AGENT_MEMORY_ENABLED and others.

    Args:
        config: The AppConfig object to set attributes on.
        env_or_toml_dict: The environment variables or a config.toml dict.
    """

    def get_optional_type(union_type: UnionType) -> Any:
        """Returns the non-None type from an Union."""
        types = get_args(union_type)
        return next((t for t in types if t is not type(None)), None)

    # helper function to set attributes based on env vars
    def set_attr_from_env(sub_config: Any, prefix=''):
        """Set attributes of a config dataclass based on environment variables."""
        for field_name, field_type in sub_config.__annotations__.items():
            # compute the expected env var name from the prefix and field name
            env_var_name = (prefix + field_name).upper()

            if hasattr(field_type, '__annotations__'):
                # nested dataclass
                nested_sub_config = getattr(sub_config, field_name)
                set_attr_from_env(nested_sub_config, prefix=field_name + '_')
            elif env_var_name in env_or_toml_dict:
                # convert the env var to the correct type and set it
                value = env_or_toml_dict[env_var_name]
                try:
                    # if it's an optional type, get the non-None type
                    if get_origin(field_type) is UnionType:
                        field_type = get_optional_type(field_type)

                    # Attempt to cast the env var to type hinted in the dataclass
                    cast_value = field_type(value)
                    setattr(sub_config, field_name, cast_value)
                except (ValueError, TypeError):
                    logger.error(
                        f'Error setting env var {env_var_name}={value}: check that the value is of the right type'
                    )

    # Start processing from the root of the config object
    set_attr_from_env(config)


def load_from_toml(config: AppConfig):
    """Load the config from the toml file. Supports both styles of config vars.

    Args:
        config: The AppConfig object to update attributes of.
    """

    # try to read the config.toml file into the config object
    toml_config = {}

    try:
        with open('config.toml', 'r', encoding='utf-8') as toml_file:
            toml_config = toml.load(toml_file)
    except FileNotFoundError:
        # the file is optional, we don't need to do anything
        return
    except toml.TomlDecodeError:
        logger.warning(
            'Cannot parse config from toml, toml values have not been applied.',
            exc_info=False,
        )
        return

    # if there was an exception or core is not in the toml, try to use the old-style toml
    if 'core' not in toml_config:
        # re-use the env loader to set the config from env-style vars
        load_from_env(config, toml_config)
        return

    core_config = toml_config['core']

    try:
        llm_config = config.llm
        if 'llm' in toml_config:
            llm_config = LLMConfig(**toml_config['llm'])

        agent_config = config.agent
        if 'agent' in toml_config:
            agent_config = AgentConfig(**toml_config['agent'])

        config = AppConfig(llm=llm_config, agent=agent_config, **core_config)
    except (TypeError, KeyError):
        logger.warning(
            'Cannot parse config from toml, toml values have not been applied.',
            exc_info=False,
        )


def finalize_config(config: AppConfig):
    """
    More tweaks to the config after it's been loaded.
    """

    # In local there is no sandbox, the workspace will have the same pwd as the host
    if config.sandbox_type == 'local':
        # TODO why do we seem to need None for these paths?
        config.workspace_mount_path_in_sandbox = config.workspace_mount_path

    if config.workspace_mount_rewrite:  # and not config.workspace_mount_path:
        # TODO why do we need to check if workspace_mount_path is None?
        base = config.workspace_base or os.getcwd()
        parts = config.workspace_mount_rewrite.split(':')
        config.workspace_mount_path = base.replace(parts[0], parts[1])

    if config.llm.embedding_base_url is None:
        config.llm.embedding_base_url = config.llm.base_url

    if config.use_host_network and platform.system() == 'Darwin':
        logger.warning(
            'Please upgrade to Docker Desktop 4.29.0 or later to use host network mode on macOS. '
            'See https://github.com/docker/roadmap/issues/238#issuecomment-2044688144 for more information.'
        )

    # TODO why was the last workspace_mount_path line unreachable?

    if config.cache_dir:
        pathlib.Path(config.cache_dir).mkdir(parents=True, exist_ok=True)


config = AppConfig()
load_from_toml(config)
load_from_env(config, os.environ)
finalize_config(config)


# Command line arguments
def get_parser():
    """
    Get the parser for the command line arguments.
    """
    parser = argparse.ArgumentParser(description='Run an agent with a specific task')
    parser.add_argument(
        '-d',
        '--directory',
        type=str,
        help='The working directory for the agent',
    )
    parser.add_argument(
        '-t', '--task', type=str, default='', help='The task for the agent to perform'
    )
    parser.add_argument(
        '-f',
        '--file',
        type=str,
        help='Path to a file containing the task. Overrides -t if both are provided.',
    )
    parser.add_argument(
        '-c',
        '--agent-cls',
        default=config.agent.name,
        type=str,
        help='The agent class to use',
    )
    parser.add_argument(
        '-m',
        '--model-name',
        default=config.llm.model,
        type=str,
        help='The (litellm) model name to use',
    )
    parser.add_argument(
        '-i',
        '--max-iterations',
        default=config.max_iterations,
        type=int,
        help='The maximum number of iterations to run the agent',
    )
    parser.add_argument(
        '-n',
        '--max-chars',
        default=config.llm.max_chars,
        type=int,
        help='The maximum number of characters to send to and receive from LLM per task',
    )
    return parser


def parse_arguments():
    """
    Parse the command line arguments.
    """
    parser = get_parser()
    args, _ = parser.parse_known_args()
    if args.directory:
        config.workspace_base = os.path.abspath(args.directory)
        print(f'Setting workspace base to {config.workspace_base}')
    return args


args = parse_arguments()