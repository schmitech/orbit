export type StreamResponse = 
  | { type: 'text'; content: string } 
  | { type: 'audio'; content: string; isFinal?: boolean }; 