import { HfInference } from '@huggingface/inference';

interface QAResponse {
  answer: string;
  score: number;
}

export async function questionAnswerWithHuggingFace(
  context: string,
  question: string
): Promise<QAResponse> {
  const verbose = process.env.VERBOSE === 'true';
  const hf = new HfInference(process.env.HUGGINGFACE_API_KEY);
  
  const result = await hf.questionAnswering({
    model: 'deepset/roberta-base-squad2',
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