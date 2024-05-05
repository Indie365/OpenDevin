export type Settings = {
  LLM_MODEL: string;
  AGENT: string;
  LANGUAGE: string;
  LLM_API_KEY: string;
  WORKSPACE: string;
};

export const DEFAULT_SETTINGS: Settings = {
  LLM_MODEL: "gpt-3.5-turbo",
  AGENT: "CodeActAgent",
  LANGUAGE: "en",
  LLM_API_KEY: "",
  WORKSPACE: "",
};

const validKeys = Object.keys(DEFAULT_SETTINGS) as (keyof Settings)[];

/**
 * Get the settings from local storage or use the default settings if not found
 */
const getSettingsInternal = (): Settings => {
  const model = localStorage.getItem("LLM_MODEL");
  const agent = localStorage.getItem("AGENT");
  const language = localStorage.getItem("LANGUAGE");
  const apiKey = localStorage.getItem(`API_KEY_${model}`);
  const workspace = localStorage.getItem("WORKSPACE");
  console.log("WOWOWOWOWOWOW");
  return {
    LLM_MODEL: model || DEFAULT_SETTINGS.LLM_MODEL,
    AGENT: agent || DEFAULT_SETTINGS.AGENT,
    LANGUAGE: language || DEFAULT_SETTINGS.LANGUAGE,
    LLM_API_KEY: apiKey || DEFAULT_SETTINGS.LLM_API_KEY,
    WORKSPACE: workspace || DEFAULT_SETTINGS.WORKSPACE,
  };
};

export const getSettings = getSettingsInternal;

/**
 * Save the settings to local storage. Only valid settings are saved.
 * @param settings - the settings to save
 */
export const saveSettings = (settings: Partial<Settings>) => {
  Object.keys(settings).forEach((key) => {
    const isValid = validKeys.includes(key as keyof Settings);
    const value = settings[key as keyof Settings];

    if (isValid && value) localStorage.setItem(key, value);
  });
};

/**
 * Get the difference between two sets of settings.
 * Useful for notifying the user of exact changes.
 *
 * @example
 * // Assuming the current settings are:
 * const updatedSettings = getSettingsDifference(
 *  { LLM_MODEL: "gpt-3.5", AGENT: "MonologueAgent", LANGUAGE: "en" },
 *  { LLM_MODEL: "gpt-3.5", AGENT: "OTHER_AGENT", LANGUAGE: "en" }
 * )
 * // updatedSettings = { AGENT: "OTHER_AGENT" }
 *
 * @returns only the settings from `newSettings` that are different from `oldSettings`.
 */
export const getSettingsDifference = (
  oldSettings: Partial<Settings>,
  newSettings: Partial<Settings>,
) => {
  const updatedSettings: Partial<Settings> = {};
  Object.keys(newSettings).forEach((key) => {
    if (
      validKeys.includes(key as keyof Settings) &&
      newSettings[key as keyof Settings] !== oldSettings[key as keyof Settings]
    ) {
      updatedSettings[key as keyof Settings] =
        newSettings[key as keyof Settings];
    }
  });

  return updatedSettings;
};
