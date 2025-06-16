import { useState } from 'react';
import type { CustomColors } from '../types/widget.types';
import { defaultCustomColors, themes } from '../constants/themes';

export const useThemeCustomization = () => {
  const [selectedTheme, setSelectedTheme] = useState('modern');
  const [customColors, setCustomColors] = useState<CustomColors>(defaultCustomColors);

  // Apply theme preset
  const applyTheme = (themeName: keyof typeof themes) => {
    setSelectedTheme(themeName);
    setCustomColors(themes[themeName].colors);
  };

  // Update individual color
  const updateColor = (colorKey: keyof CustomColors, value: string) => {
    setCustomColors({
      ...customColors,
      [colorKey]: value
    });
  };

  // Update multiple colors at once
  const updateColors = (colorUpdates: Partial<CustomColors>) => {
    setCustomColors({
      ...customColors,
      ...Object.fromEntries(
        Object.entries(colorUpdates).map(([key, value]) => [key, value || customColors[key as keyof CustomColors]])
      )
    });
  };

  // Reset to default colors
  const resetColors = () => {
    setCustomColors(defaultCustomColors);
    setSelectedTheme('modern');
  };

  return {
    selectedTheme,
    customColors,
    setCustomColors,
    applyTheme,
    updateColor,
    updateColors,
    resetColors
  };
};