import { useColorScheme } from 'react-native';
import { colors, ThemeColors } from '../theme/colors';
import { useThemeStore } from '../stores/themeStore';

export function useTheme() {
  const systemScheme = useColorScheme();
  const mode = useThemeStore((s) => s.mode);
  const loaded = useThemeStore((s) => s.loaded);
  const setThemeMode = useThemeStore((s) => s.setThemeMode);

  const isDark =
    mode === 'system' ? systemScheme === 'dark' : mode === 'dark';

  const theme: ThemeColors = isDark ? colors.dark : colors.light;

  return { theme, isDark, mode, setThemeMode, loaded };
}
