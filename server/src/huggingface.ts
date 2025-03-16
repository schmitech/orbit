import { HfInference } from '@huggingface/inference';

interface QAResponse {
  answer: string;
  score: number;
}

export async function questionAnswerWithHuggingFace(
  context: string,
  question: string,
  config: any
): Promise<QAResponse> {
  const verbose = config.general?.verbose === 'true';
  const hf = new HfInference(config.huggingface.api_key);
  
  const result = await hf.questionAnswering({
    model: config.huggingface.model || 'deepset/roberta-base-squad2',
    inputs: {
      question: question,
      context: context
    }
  });
  
  if (verbose) {
    console.log('HuggingFace response:', result);
  }
  
  return {
    answer: result.answer,
    score: result.score
  };
}