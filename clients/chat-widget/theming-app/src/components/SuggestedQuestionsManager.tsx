import React from 'react';
import { Button } from './Button';

interface SuggestedQuestion {
  text: string;
  query: string;
}

interface SuggestedQuestionsManagerProps {
  questions: SuggestedQuestion[];
  maxQuestionLength: number;
  maxQueryLength: number;
  onUpdateQuestion: (index: number, field: 'text' | 'query', value: string) => void;
  onAddQuestion: () => void;
  onRemoveQuestion: (index: number) => void;
}

export const SuggestedQuestionsManager: React.FC<SuggestedQuestionsManagerProps> = ({
  questions,
  maxQuestionLength,
  maxQueryLength,
  onUpdateQuestion,
  onAddQuestion,
  onRemoveQuestion
}) => {
  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-gray-900">Suggested Questions</h3>
        <Button
          onClick={onAddQuestion}
          disabled={questions.length >= 6}
          variant="ghost"
          size="sm"
        >
          + Add Question
        </Button>
      </div>
      
      <div className="space-y-3">
        {questions.map((question, index) => (
          <div key={index} className="p-3 border border-black rounded-lg relative">
            <Button
              onClick={() => onRemoveQuestion(index)}
              variant="ghost"
              size="sm"
              className="absolute top-2 right-2 text-red-600 hover:text-red-700"
            >
              Remove
            </Button>
            <div className="space-y-2 pr-20">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">
                  Display Text (max {maxQuestionLength} chars)
                </label>
                <div className="flex gap-2">
                  <div className="flex-1 relative">
                    <input
                      type="text"
                      value={question.text}
                      onChange={(e) => {
                        const value = e.target.value;
                        // Enforce the max length during typing
                        if (value.length <= maxQuestionLength) {
                          onUpdateQuestion(index, 'text', value);
                        } else {
                          onUpdateQuestion(index, 'text', value.substring(0, maxQuestionLength));
                        }
                      }}
                      maxLength={maxQuestionLength}
                      className="w-full px-3 py-2 pr-16 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                      placeholder="Button text"
                    />
                    <div className="absolute right-3 top-1/2 transform -translate-y-1/2 pointer-events-none">
                      <span className="text-xs text-gray-400 bg-white px-1">
                        {question.text.length}/{maxQuestionLength}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
              
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">
                  Query (max {maxQueryLength} chars)
                </label>
                <div className="relative">
                  <input
                    type="text"
                    value={question.query}
                    onChange={(e) => {
                      const value = e.target.value;
                      // Enforce the max length during typing
                      if (value.length <= maxQueryLength) {
                        onUpdateQuestion(index, 'query', value);
                      } else {
                        onUpdateQuestion(index, 'query', value.substring(0, maxQueryLength));
                      }
                    }}
                    maxLength={maxQueryLength}
                    className="w-full px-3 py-2 pr-16 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                    placeholder="Query sent to API"
                  />
                  <div className="absolute right-3 top-1/2 transform -translate-y-1/2 pointer-events-none">
                    <span className="text-xs text-gray-400 bg-white px-1">
                      {question.query.length}/{maxQueryLength}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};