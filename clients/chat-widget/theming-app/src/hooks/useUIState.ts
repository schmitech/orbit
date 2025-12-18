import { useState } from 'react';
import type { ExpandedSections, TabType } from '../types/widget.types';

export const useUIState = () => {
  const [activeTab, setActiveTab] = useState<TabType>('theme');
  const [copied, setCopied] = useState(false);
  const [expandedSections, setExpandedSections] = useState<ExpandedSections>({
    mainColors: true,
    textColors: true,
    messageBubbles: true,
    chatButton: true,
    iconSelection: true
  });

  // Toggle section expansion
  const toggleSection = (section: keyof ExpandedSections) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section]
    }));
  };

  // Handle copy feedback
  const handleCopySuccess = () => {
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Expand all sections
  const expandAllSections = () => {
    setExpandedSections({
      mainColors: true,
      textColors: true,
      messageBubbles: true,
      chatButton: true,
      iconSelection: true
    });
  };

  // Collapse all sections
  const collapseAllSections = () => {
    setExpandedSections({
      mainColors: false,
      textColors: false,
      messageBubbles: false,
      chatButton: false,
      iconSelection: false
    });
  };

  return {
    activeTab,
    setActiveTab,
    copied,
    setCopied,
    expandedSections,
    setExpandedSections,
    toggleSection,
    handleCopySuccess,
    expandAllSections,
    collapseAllSections
  };
};