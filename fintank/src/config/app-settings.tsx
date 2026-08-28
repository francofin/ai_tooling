import { createContext, useContext, useState, ReactNode } from 'react';

// Define the structure of the settings
interface AppSettings {
  appBoxedLayout: boolean;
  appContentClass: string;
  appContentFullHeight: boolean;
  appContentNone: boolean;
  appHeaderNone: boolean;
  appSidebarNone: boolean;
  appSidebarCollapsed: boolean;
  appFooter: boolean;
  appTopNav: boolean;
}

interface AppSettingsContextValue {
  settings: AppSettings;
  updateSettings: (newSettings: Partial<AppSettings>) => void;
}

// Default app settings
const defaultSettings: AppSettings = {
  appBoxedLayout: false,
  appContentClass: '',
  appContentFullHeight: false,
  appContentNone: false,
  appHeaderNone: false,
  appSidebarNone: false,
  appSidebarCollapsed: false,
  appFooter: false,
  appTopNav: false,
};

const AppSettingsContext = createContext<AppSettingsContextValue | undefined>(
  undefined
);

export const AppSettingsProvider = ({ children }: { children: ReactNode }) => {
  const [settings, setSettings] = useState(defaultSettings);

  const updateSettings = (newSettings: Partial<AppSettings>) => {
    setSettings((prevSettings) => ({ ...prevSettings, ...newSettings }));
  };

  return (
    <AppSettingsContext.Provider value={{ settings, updateSettings }}>
      {children}
    </AppSettingsContext.Provider>
  );
};

export const useAppSettings = (): AppSettingsContextValue => {
  const context = useContext(AppSettingsContext);
  if (!context) {
    throw new Error('useAppSettings must be used within an AppSettingsProvider');
  }
  return context;
};