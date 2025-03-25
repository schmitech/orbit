export interface ChatMessage {
  id: string;
  content: string;
  sender: 'user' | 'bot';
  timestamp: Date;
}

export interface ThemeConfig {
  primaryColor?: string;
  size?: 'small' | 'medium' | 'large';
  font?: string;
}

export interface MessageConfig {
  greeting?: string;
  title?: string;
}

export interface PositionConfig {
  bottom?: number;
  right?: number;
}

export interface DimensionConfig {
  width?: number;
  height?: number;
}

export interface ApiConfig {
  endpoint: string;
}

export interface ChatbotConfig {
  theme?: ThemeConfig;
  messages?: MessageConfig;
  position?: PositionConfig;
  dimensions?: DimensionConfig;
  api: ApiConfig;
}