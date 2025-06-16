// Style constants and CSS for the ChatWidget
export const DEFAULT_MAX_SUGGESTED_QUESTION_LENGTH = 120;
export const DEFAULT_MAX_SUGGESTED_QUESTION_QUERY_LENGTH = 200;

export let CHAT_CONSTANTS = {
    MAX_MESSAGE_LENGTH: 250 as number,
    MAX_SUGGESTED_QUESTION_LENGTH: DEFAULT_MAX_SUGGESTED_QUESTION_LENGTH as number,
    MAX_SUGGESTED_QUESTION_QUERY_LENGTH: DEFAULT_MAX_SUGGESTED_QUESTION_QUERY_LENGTH as number,
    WINDOW_DIMENSIONS: {
      HEIGHT: '600px',
      MAX_HEIGHT: 'calc(100vh - 80px)',
      BREAKPOINTS: {
        SM: 640,
        MD: 768,
        LG: 1024,
      },
      WIDTHS: {
        SM: '480px',
        MD: '600px',
        LG: '700px',
      },
    } as const,
    SCROLL_THRESHOLDS: {
      BOTTOM_THRESHOLD: 10,
      TOP_THRESHOLD: 10,
      SHOW_SCROLL_TOP_OFFSET: 200,
    } as const,
    ANIMATIONS: {
      SCROLL_TIMEOUT: 300,
      TOGGLE_DELAY: 100,
      ANIMATION_SCROLL_INTERVAL: 100,
      COPY_FEEDBACK_DURATION: 2000,
      VISIBILITY_SKIP_THRESHOLD: 1000,
    } as const,
    BUTTON_SIZES: {
      CHAT_BUTTON: { width: '68px', height: '68px' },
      SEND_BUTTON: { width: '52px', height: '52px' },
      ICON_SIZES: {
        HEADER: 28,
        WELCOME: 56,
        BUTTON: 20,
        SEND: 24,
        MINIMIZE: 28,
      },
    } as const,
  };
  
  /**
   * Global CSS styles for the ChatWidget component
   */
  export const CHAT_WIDGET_STYLES = `
  body, button, input, textarea {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
  }
  
  /* Complete focus ring removal - covers all browsers and scenarios */
  textarea,
  textarea:focus,
  textarea:focus-visible,
  input,
  input:focus,
  input:focus-visible {
    outline: none !important;
    box-shadow: none !important;
    border-color: inherit !important;
    -webkit-appearance: none !important;
    -moz-appearance: none !important;
    -webkit-tap-highlight-color: transparent !important;
  }
  
  /* Alternative: Uncomment for subtle light focus ring instead of complete removal */
  /*
  textarea:focus,
  textarea:focus-visible {
    outline: 2px solid rgba(203, 213, 225, 0.4) !important;
    outline-offset: -1px !important;
    box-shadow: 0 0 0 1px rgba(203, 213, 225, 0.2) !important;
  }
  */
  
  /* Remove webkit/safari specific styling */
  textarea::-webkit-input-placeholder,
  input::-webkit-input-placeholder {
    -webkit-appearance: none;
  }
  
  /* Ensure buttons also don't show focus rings */
  button:focus,
  button:focus-visible {
    outline: none !important;
    box-shadow: none !important;
  }

  /* Enhanced animations for modern feel */
  @keyframes slideInUp {
    0% { 
      opacity: 0; 
      transform: translateY(20px) scale(0.95); 
    }
    100% { 
      opacity: 1; 
      transform: translateY(0) scale(1); 
    }
  }

  @keyframes slideOutDown {
    0% { 
      opacity: 1; 
      transform: translateY(0) scale(1); 
    }
    100% { 
      opacity: 0; 
      transform: translateY(20px) scale(0.95); 
    }
  }

  .animate-slide-in-up {
    animation: slideInUp 0.3s cubic-bezier(0.4, 0, 0.2, 1) forwards;
  }

  .animate-slide-out-down {
    animation: slideOutDown 0.2s cubic-bezier(0.4, 0, 0.2, 1) forwards;
  }

  @keyframes pulseGlow {
    0%, 100% { 
      box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.4);
    }
    50% { 
      box-shadow: 0 0 0 8px rgba(59, 130, 246, 0);
    }
  }

  .animate-pulse-glow {
    animation: pulseGlow 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
  }

  @keyframes messageEntry {
    0% { 
      opacity: 0; 
      transform: translateY(10px) scale(0.98);
    }
    100% { 
      opacity: 1; 
      transform: translateY(0) scale(1);
    }
  }

  .animate-message-entry {
    animation: messageEntry 0.4s cubic-bezier(0.4, 0, 0.2, 1) forwards;
  }

  @keyframes buttonHover {
    0% { transform: translateY(0) scale(1); }
    100% { transform: translateY(-2px) scale(1.05); }
  }

  .animate-button-hover:hover {
    animation: buttonHover 0.2s cubic-bezier(0.4, 0, 0.2, 1) forwards;
  }
  
  @keyframes fadeInOut {
    0% { opacity: 0; transform: translateY(4px); }
    20% { opacity: 1; transform: translateY(0); }
    80% { opacity: 1; transform: translateY(0); }
    100% { opacity: 0; transform: translateY(-4px); }
  }
  .animate-fade-in-out {
    animation: fadeInOut 2s ease-in-out forwards;
  }
  
  @keyframes bounce-gentle {
    0%, 100% { transform: translateY(0); }
    50% { transform: translateY(-8px); }
  }
  .animate-bounce-gentle {
    animation: bounce-gentle 3s ease-in-out infinite;
    animation-delay: 2s;
  }

  @keyframes float {
    0%, 100% { transform: translateY(0px) rotate(0deg); }
    33% { transform: translateY(-3px) rotate(1deg); }
    66% { transform: translateY(2px) rotate(-1deg); }
  }
  .animate-float {
    animation: float 6s ease-in-out infinite;
  }
  
  @keyframes dotBlink {
    0%, 50%, 100% { opacity: 0.3; }
    25%, 75% { opacity: 1; }
  }
  .animate-dots {
    display: inline-flex;
    margin-left: 4px;
  }
  .animate-dots .dot {
    font-size: 1.2em;
    line-height: 0.5;
    opacity: 0.3;
    animation: dotBlink 1.6s infinite;
    color: #6b7280;
  }
  .animate-dots .dot:nth-child(1) {
    animation-delay: 0s;
  }
  .animate-dots .dot:nth-child(2) {
    animation-delay: 0.3s;
  }
  .animate-dots .dot:nth-child(3) {
    animation-delay: 0.6s;
  }

  /* Glassmorphism effects */
  .glass-effect {
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    background: rgba(255, 255, 255, 0.8);
    border: 1px solid rgba(255, 255, 255, 0.3);
  }

  .glass-effect-dark {
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    background: rgba(30, 41, 59, 0.8);
    border: 1px solid rgba(255, 255, 255, 0.1);
  }

  /* Custom scrollbar */
  .custom-scrollbar::-webkit-scrollbar {
    width: 6px;
  }

  .custom-scrollbar::-webkit-scrollbar-track {
    background: rgba(0, 0, 0, 0.05);
    border-radius: 3px;
  }

  .custom-scrollbar::-webkit-scrollbar-thumb {
    background: rgba(0, 0, 0, 0.2);
    border-radius: 3px;
    transition: background 0.2s ease;
  }

  .custom-scrollbar::-webkit-scrollbar-thumb:hover {
    background: rgba(0, 0, 0, 0.3);
  }

  /* Enhanced shadows */
  .shadow-elegant {
    box-shadow: 
      0 10px 25px -5px rgba(0, 0, 0, 0.1),
      0 8px 10px -6px rgba(0, 0, 0, 0.1),
      0 0 0 1px rgba(255, 255, 255, 0.05);
  }

  .shadow-soft {
    box-shadow: 
      0 4px 6px -1px rgba(0, 0, 0, 0.1),
      0 2px 4px -1px rgba(0, 0, 0, 0.06);
  }

  .shadow-floating {
    box-shadow: 
      0 20px 25px -5px rgba(0, 0, 0, 0.1),
      0 10px 10px -5px rgba(0, 0, 0, 0.04);
  }
  
  .prose {
    max-width: 100%;
  }
  
  .prose > * {
    margin-top: 0 !important;
    margin-bottom: 0.5em !important;
  }
  
  .prose p {
    margin: 0 0 0.5em 0 !important;
    padding: 0;
    line-height: 1.6;
  }
  
  .prose p:last-child {
    margin-bottom: 0 !important;
  }
  
  .prose ul,
  .prose ol {
    margin-top: 0.5em !important;
    margin-bottom: 0.5em !important;
    padding-left: 1.5em !important;
  }
  
  .prose li {
    margin-bottom: 0.25em !important;
    padding-left: 0.25em !important;
    line-height: 1.5;
  }
  
  .prose li p {
    margin: 0 !important;
  }
  
  .prose li + li {
    margin-top: 0.1em !important;
  }
  
  .prose h1, .prose h2, .prose h3, .prose h4, .prose h5, .prose h6 {
    margin-top: 1em !important;
    margin-bottom: 0.5em !important;
    font-weight: 600;
  }

  /* Button enhancements */
  .btn-modern {
    position: relative;
    overflow: hidden;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  }

  .btn-modern::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: linear-gradient(135deg, rgba(255, 255, 255, 0.2), rgba(255, 255, 255, 0));
    opacity: 0;
    transition: opacity 0.3s ease;
  }

  .btn-modern:hover::before {
    opacity: 1;
  }

  /* Input enhancements */
  .input-modern {
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  }

  .input-modern:focus {
    transform: translateY(-1px);
  }
  `;
  
  /**
   * Helper functions for responsive window dimensions
   */
  export const getResponsiveWidth = (windowWidth: number): string => {
    const { BREAKPOINTS, WIDTHS } = CHAT_CONSTANTS.WINDOW_DIMENSIONS;
    
    if (windowWidth < BREAKPOINTS.SM) return '100%';
    if (windowWidth < BREAKPOINTS.MD) return WIDTHS.SM;
    if (windowWidth < BREAKPOINTS.LG) return WIDTHS.MD;
    return WIDTHS.LG;
  };
  
  export const getResponsiveMinWidth = (windowWidth: number): string => {
    return windowWidth < CHAT_CONSTANTS.WINDOW_DIMENSIONS.BREAKPOINTS.SM 
      ? '100%' 
      : CHAT_CONSTANTS.WINDOW_DIMENSIONS.WIDTHS.SM;
  };
  
  /**
   * Font family constant for consistent typography
   */
  export const FONT_FAMILY = '-apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif';
  
  /**
   * Character count styling helper
   */
  export const getCharacterCountStyle = (length: number, maxLength: number) => ({
    color: length >= maxLength * 0.9 ? '#ef4444' : '#6b7280',
    backgroundColor: length >= maxLength * 0.9 
      ? 'rgba(239, 68, 68, 0.1)' 
      : 'rgba(107, 114, 128, 0.1)',
    fontSize: '0.7rem'
  });

// Allow runtime override with flexible typing for number values
export function setChatConstants(config: Partial<{
  MAX_MESSAGE_LENGTH?: number;
  MAX_SUGGESTED_QUESTION_LENGTH?: number;
  MAX_SUGGESTED_QUESTION_QUERY_LENGTH?: number;
}>) {
  Object.assign(CHAT_CONSTANTS, config);
}