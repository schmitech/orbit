// Character limits based on widget's styles.ts constants
export const WIDGET_LIMITS = {
  // Based on DEFAULT_MAX_SUGGESTED_QUESTION_LENGTH from styles.ts
  MAX_SUGGESTED_QUESTION_LENGTH: 120,
  // Based on DEFAULT_MAX_SUGGESTED_QUESTION_QUERY_LENGTH from styles.ts  
  MAX_SUGGESTED_QUESTION_QUERY_LENGTH: 200,
  // Minimum values for reasonable UX
  MIN_SUGGESTED_QUESTION_LENGTH: 10,
  MIN_SUGGESTED_QUESTION_QUERY_LENGTH: 10,
  // Maximum values for performance and UX
  MAX_SUGGESTED_QUESTION_LENGTH_HARD: 200,
  MAX_SUGGESTED_QUESTION_QUERY_LENGTH_HARD: 1000
} as const;

// Helper function to get limit descriptions
export const getLimitDescriptions = () => ({
  questionLength: {
    min: WIDGET_LIMITS.MIN_SUGGESTED_QUESTION_LENGTH,
    max: WIDGET_LIMITS.MAX_SUGGESTED_QUESTION_LENGTH_HARD,
    default: WIDGET_LIMITS.MAX_SUGGESTED_QUESTION_LENGTH,
    description: "Controls how much text is shown on suggestion buttons"
  },
  queryLength: {
    min: WIDGET_LIMITS.MIN_SUGGESTED_QUESTION_QUERY_LENGTH,
    max: WIDGET_LIMITS.MAX_SUGGESTED_QUESTION_QUERY_LENGTH_HARD,
    default: WIDGET_LIMITS.MAX_SUGGESTED_QUESTION_QUERY_LENGTH,
    description: "Controls the maximum length of queries sent to your API"
  }
});

// Helper function to get the current limits
export const getWidgetLimits = () => {
  // Try to get limits from the widget if it's loaded
  if (typeof window !== 'undefined' && window.ChatbotWidget?.getCurrentConfig) {
    try {
      const config = window.ChatbotWidget.getCurrentConfig();
      if (config?.CHAT_CONSTANTS) {
        return {
          MAX_SUGGESTED_QUESTION_LENGTH: config.CHAT_CONSTANTS.MAX_SUGGESTED_QUESTION_LENGTH || WIDGET_LIMITS.MAX_SUGGESTED_QUESTION_LENGTH,
          MAX_SUGGESTED_QUESTION_QUERY_LENGTH: config.CHAT_CONSTANTS.MAX_SUGGESTED_QUESTION_QUERY_LENGTH || WIDGET_LIMITS.MAX_SUGGESTED_QUESTION_QUERY_LENGTH,
          MIN_SUGGESTED_QUESTION_LENGTH: WIDGET_LIMITS.MIN_SUGGESTED_QUESTION_LENGTH,
          MIN_SUGGESTED_QUESTION_QUERY_LENGTH: WIDGET_LIMITS.MIN_SUGGESTED_QUESTION_QUERY_LENGTH,
          MAX_SUGGESTED_QUESTION_LENGTH_HARD: WIDGET_LIMITS.MAX_SUGGESTED_QUESTION_LENGTH_HARD,
          MAX_SUGGESTED_QUESTION_QUERY_LENGTH_HARD: WIDGET_LIMITS.MAX_SUGGESTED_QUESTION_QUERY_LENGTH_HARD
        };
      }
    } catch (error) {
      console.warn('Could not get widget limits from ChatbotWidget, using defaults:', error);
    }
  }
  
  return WIDGET_LIMITS;
};
