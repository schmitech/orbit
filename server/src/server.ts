import express from 'express';
import cors from 'cors';
import { ChromaClient } from 'chromadb';
import { Ollama } from '@langchain/community/llms/ollama';
import { RunnableSequence } from '@langchain/core/runnables';
import { StringOutputParser } from '@langchain/core/output_parsers';
import { ChromaRetriever } from './chromaRetriever';
import { Document } from '@langchain/core/documents';
import { PromptTemplate } from "@langchain/core/prompts";
import { OllamaEmbeddings } from '@langchain/community/embeddings/ollama';
import { OllamaEmbeddingWrapper } from './ollamaEmbeddingWrapper';
import path from 'path';
import { fileURLToPath } from 'node:url';
import { questionAnswerWithHuggingFace } from './huggingface';
import fs from 'fs/promises';
import yaml from 'js-yaml';

// Define config interface
interface AppConfig {
  ollama: {
    base_url: string;
    temperature: number | string;
    top_p: number | string;
    top_k: number | string;
    repeat_penalty: number | string;
    num_predict: number | string;
    num_ctx: number | string;
    num_threads: number | string;
    model: string;
    embed_model: string;
  };
  huggingface: {
    api_key: string;
    model: string;
  };
  chroma: {
    host: string;
    port: number | string;
    collection: string;
  };
  eleven_labs: {
    api_key: string;
    voice_id: string;
  };
  system: {
    prompt: string;
  };
  general: {
    verbose: string;
  };
}

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Replace env vars reset with config loading
// Load config.yaml instead of .env
let config: AppConfig;
try {
  const configPath = path.resolve(__dirname, '../config.yaml');
  console.log('Loading config from:', configPath);
  
  const configFile = await fs.readFile(configPath, 'utf-8');
  config = yaml.load(configFile) as AppConfig;
  
  if (config.general?.verbose === 'true') {
    console.log('Loaded configuration:', JSON.stringify(config, null, 2));
  }
} catch (error) {
  console.error('Error reading config file:', error);
  process.exit(1);
}

// Add this after the config loading
async function verifyOllamaConnection() {
  try {
    const response = await fetch(`${config.ollama.base_url}/api/tags`);
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    console.log('Ollama connection successful');
  } catch (error) {
    console.error('Ollama connection failed:', error);
    process.exit(1);
  }
}

// Add this before initializing the Ollama client
await verifyOllamaConnection();

const app = express();
app.use(cors());
app.use(express.json());

const port = 3000;

// Initialize ChromaDB with proper configuration
const client = new ChromaClient({
    path: `http://${config.chroma.host}:${config.chroma.port}`
});

// Check if system prompt exists in config
if (!config.system?.prompt) {
  console.error('No system prompt found in config.yaml. Exiting...');
  process.exit(1);
}

// Use the system prompt directly from config
const systemPrompt = config.system.prompt;

if (config.general?.verbose === 'true') {
  console.log('Using system prompt from config.yaml:');
  console.log(systemPrompt.substring(0, 100) + '...');
  console.log('Full system prompt length:', systemPrompt.length);
}

const llm = new Ollama({
  baseUrl: config.ollama.base_url,
  model: config.ollama.model,
  temperature: parseFloat(String(config.ollama.temperature)),
  system: systemPrompt,
  numPredict: parseInt(String(config.ollama.num_predict)),
  repeatPenalty: parseFloat(String(config.ollama.repeat_penalty)),
  numCtx: parseInt(String(config.ollama.num_ctx)),
  numThread: parseInt(String(config.ollama.num_threads)),
  top_p: parseFloat(String(config.ollama.top_p)),
  top_k: parseInt(String(config.ollama.top_k)),
  
  fetch: async (input: RequestInfo, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.url;
    if (config.general?.verbose === 'true') {
      console.log('\n--- Ollama API Call ---');
      console.log('Endpoint:', url.replace(config.ollama.base_url!, ''));
      
      if (init?.body) {
        const body = JSON.parse(init.body.toString());
        console.log('\nFull Request Body:');
        console.log(JSON.stringify(body, null, 2));
        console.log('\nSystem Prompt:', body.system);
        console.log('\nUser Prompt:', body.prompt);
        console.log('\nOptions:', body.options);
      }
      
      const start = Date.now();
      const response = await fetch(input, init);
      console.log(`\nDuration: ${Date.now() - start}ms`);
      console.log('Status:', response.status);
      
      return response;
    }
    return fetch(input, init);
  }
} as any);

// Initialize Ollama embeddings with config
const embeddings = new OllamaEmbeddings({
  baseUrl: config.ollama.base_url,
  model: config.ollama.embed_model,
});

// Create the wrapper instance
const embeddingWrapper = new OllamaEmbeddingWrapper(embeddings);

// Use the wrapper in Chroma collection methods
let collection;
try {
  collection = await client.getCollection({
    name: config.chroma.collection || 'qa-chatbot',
    embeddingFunction: embeddingWrapper
  });
  
  console.log('Successfully connected to existing Chroma collection: ' + config.chroma.collection);
  
} catch (error) {
  console.error('Failed to get Chroma collection:', error);
  process.exit(1);
}

const retriever = new ChromaRetriever(collection, embeddingWrapper);

// Helper function to format documents as string
const formatDocuments = (docs: Document[]): string => {
  const verbose = config.general?.verbose === 'true';
  
  if (verbose) {
    console.log('\n=== Format Documents ===');
    console.log('Number of documents:', docs.length);
    if (docs.length > 0) {
      console.log('First document content:', docs[0].pageContent);
      console.log('First document metadata:', JSON.stringify(docs[0].metadata, null, 2));
    }
  }
  
  // Check if we have any documents
  if (!docs.length) {
    console.error('No documents returned from retriever');
    return 'NO_RELEVANT_CONTEXT';
  }
  
  // Check if the document is a general flag
  if (docs[0]?.metadata?.isGeneral) {
    if (verbose) {
      console.log('General document flag detected');
    }
    return 'NO_RELEVANT_CONTEXT';
  }
  
  // Check for empty content
  if (!docs[0].pageContent || docs[0].pageContent.trim() === '') {
    console.error('Empty document content returned');
    return 'NO_RELEVANT_CONTEXT';
  }
  
  // If the document has metadata with an answer field, return just that answer
  if (docs[0]?.metadata?.answer) {
    if (verbose) {
      console.log('\nUsing Answer from Metadata:');
      console.log('Answer:', docs[0].metadata.answer);
      console.log('Distance:', docs[0].metadata.distance || 'N/A');
    }
    return docs[0].metadata.answer;
  }
  
  // Fallback to original behavior if no metadata
  if (verbose) {
    console.log('\nUsing Document Content (Fallback):');
    console.log('Content:', docs[0].pageContent);
  }
  return docs[0].pageContent;
};

// Add new type for backend selection
type Backend = 'ollama' | 'hf';

// Add command line argument parsing
const backend: Backend = process.argv[2] as Backend || 'ollama';
if (!['ollama', 'hf'].includes(backend)) {
  console.error('Invalid backend specified. Use either "ollama" or "hf"');
  process.exit(1);
}

if (config.general?.verbose === 'true') {
  console.log(`Using ${backend} backend`);
  console.log('Environment Variables:');
  const commonVars = {
    CHROMA_HOST: config.chroma.host,
    CHROMA_PORT: config.chroma.port,
    CHROMA_COLLECTION: config.chroma.collection,
    VERBOSE: config.general.verbose,
  };
  console.log(commonVars);
}

// Modify the chain creation to add logging
const createChain = (backend: Backend) => {
  const verbose = config.general?.verbose === 'true';
  
  if (verbose) {
    console.log('\n=== Chain Configuration ===');
    console.log('System prompt length:', systemPrompt.length);
    console.log('System prompt preview:', systemPrompt.substring(0, 100) + '...');
  }
  
  if (backend === 'ollama') {
    return RunnableSequence.from([
      async (input: { query: string }) => {
        if (verbose) {
          console.log('\n=== Starting Document Retrieval ===');
          console.log('Query:', input.query);
        }
        
        const docs = await retriever.getRelevantDocuments(input.query);
        if (verbose) {
          console.log('Retrieved documents count:', docs.length);
        }
        
        const context = formatDocuments(docs);
        if (verbose) {
          console.log('\n=== Final Context ===');
          console.log(context);
        }
        
        // Handle the case where no relevant context is found
        if (context === 'NO_RELEVANT_CONTEXT') {
          return {
            context: "NO_RELEVANT_CONTEXT",
            question: input.query,
            system: systemPrompt,
          };
        }
        
        return {
          context,
          question: input.query,
          system: systemPrompt,
        };
      },
      PromptTemplate.fromTemplate(`SYSTEM: {system}

CONTEXT: {context}

USER QUESTION: {question}

ANSWER:`),
      async (input: string) => {
        if (verbose) {
          console.log('\n=== Final Prompt to Ollama ===');
          console.log('Complete Prompt:');
          console.log(input);
          console.log('\nPrompt Length:', input.length);
        }
        const response = await llm.invoke(input);
        if (verbose) {
          console.log('\n=== Ollama Response ===');
          console.log(response);
        }
        return response;
      },
      new StringOutputParser(),
    ]);
  } else {
    // HuggingFace QA chain
    return RunnableSequence.from([
      async (input: { query: string }) => {
        const docs = await retriever.getRelevantDocuments(input.query);
        const context = formatDocuments(docs);
        
        if (context === 'NO_RELEVANT_CONTEXT') {
          return {
            context: "NO_RELEVANT_CONTEXT",
            question: input.query,
            system: systemPrompt,
            directAnswer: "I don't have specific information about that in my database."
          };
        }

        const qaResult = await questionAnswerWithHuggingFace(context, input.query, config);
        
        // If confidence is too low, fall back to Ollama
        if (qaResult.score < 0.1) {
          return {
            context,
            question: input.query,
            system: systemPrompt,
            useOllama: true,
          };
        }

        return {
          answer: qaResult.answer,
          context,
          score: qaResult.score,
        };
      },
      async (input: any) => {
        if (input.directAnswer) {
          return input.directAnswer;
        }
        
        if (input.useOllama) {
          const prompt = PromptTemplate.fromTemplate(`SYSTEM: {system}

CONTEXT: {context}

USER QUESTION: {question}

ANSWER:`);
          return prompt.format(input);
        }
        
        return `Based on the provided information (confidence: ${Math.round(input.score * 100)}%), ${input.answer}`;
      },
      input => input.useOllama ? llm : new StringOutputParser(),
      new StringOutputParser(),
    ]);
  }
};

const chain = createChain(backend);

app.post('/chat', async (req, res) => {
  const { message, voiceEnabled } = req.body;

  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');

  try {
    let textBuffer = '';
    let isFirstChunk = true;
    
    const stream = await chain.stream({ query: message });
    
    for await (const chunk of stream) {
      if (chunk) {
        textBuffer += chunk;
        res.write(JSON.stringify({ type: 'text', content: chunk }) + '\n');

        // Start voice generation earlier with smaller first chunk
        if (voiceEnabled && isFirstChunk && textBuffer.length >= 50) {  // Reduced from 100 to 50
          const currentText = textBuffer;
          textBuffer = '';
          isFirstChunk = false;

          // Reduced initial delay
          await new Promise(resolve => setTimeout(resolve, 300));  // Reduced from 1000 to 300
          try {
            await generateAudioChunk(currentText, res);
          } catch (error) {
            console.error('First chunk audio generation failed:', error);
          }
        }
        // Process subsequent chunks more frequently
        else if (voiceEnabled && !isFirstChunk && (
          (textBuffer.match(/[.!?]\s*$/) && textBuffer.length >= 30) ||  // Reduced from 50 to 30
          textBuffer.length >= 100  // Reduced from 150 to 100
        )) {
          const currentText = textBuffer;
          textBuffer = '';

          // Reduced delay between chunks
          await new Promise(resolve => setTimeout(resolve, 200));  // Reduced from 800 to 200
          try {
            await generateAudioChunk(currentText, res);
          } catch (error) {
            console.error('Audio generation failed:', error);
          }
        }
      }
    }
    
    // Handle any remaining text with minimal delay
    if (voiceEnabled && textBuffer.trim()) {
      await new Promise(resolve => setTimeout(resolve, 100));  // Reduced from 800 to 100
      try {
        await generateAudioChunk(textBuffer.trim(), res, true);
      } catch (error) {
        console.error('Final chunk audio generation failed:', error);
      }
    }
    
    res.end();
  } catch (error) {
    console.error('Error:', error);
    res.write(JSON.stringify({ type: 'text', content: 'An error occurred while processing your request.' }) + '\n');
    res.end();
  }
});

async function generateAudioChunk(text: string, res: any, isFinal: boolean = false) {
  console.log('Generating audio for:', text);

  const response = await fetch(
    `https://api.elevenlabs.io/v1/text-to-speech/${config.eleven_labs.voice_id}/stream`,
    {
      method: 'POST',
      headers: {
        'Accept': 'audio/mpeg',
        'Content-Type': 'application/json',
        'xi-api-key': config.eleven_labs.api_key || '',
      },
      body: JSON.stringify({
        text,
        model_id: 'eleven_multilingual_v1',
        voice_settings: {
          stability: 0.5,              // Reduced for more natural variation
          similarity_boost: 0.6,       // Reduced for more expressive speech
          style: 0.35,                 // Increased for more casual style
          speaking_rate: 1.1,          // Slightly faster for conversational feel
          use_speaker_boost: true      // Enhanced clarity for voice calls
        },
      }),
    }
  );

  if (!response.ok) {
    throw new Error(`Audio generation failed: ${response.status} ${response.statusText}`);
  }
    
  const audioBuffer = await response.arrayBuffer();
  const base64Audio = Buffer.from(audioBuffer).toString('base64');
    
  console.log('Audio generated successfully, length:', base64Audio.length);

  res.write(JSON.stringify({
    type: 'audio',
    content: base64Audio,
    isFinal,
  }) + '\n');
}

// Add health check endpoint
app.get('/health', async (req, res) => {
  try {
    // Check Ollama status
    const ollamaStatus: { 
      status: string; 
      statusCode?: number; 
      error?: string 
    } = { status: 'unknown' };
    
    try {
      const ollamaResponse = await fetch(`${config.ollama.base_url}/api/tags`);
      ollamaStatus.status = ollamaResponse.ok ? 'healthy' : 'unhealthy';
      ollamaStatus.statusCode = ollamaResponse.status;
    } catch (error: any) {
      ollamaStatus.status = 'unhealthy';
      ollamaStatus.error = error.message;
    }

    // Check ChromaDB status
    const chromaStatus: { 
      status: string; 
      error?: string 
    } = { status: 'unknown' };
    
    try {
      await client.heartbeat();
      chromaStatus.status = 'healthy';
    } catch (error: any) {
      chromaStatus.status = 'unhealthy';
      chromaStatus.error = error.message;
    }

    // Check ElevenLabs status (optional, only if voice is used)
    const elevenLabsStatus: { 
      status: string; 
      statusCode?: number; 
      error?: string 
    } = { status: 'unknown' };
    
    if (config.eleven_labs?.api_key) {
      try {
        const elevenLabsResponse = await fetch('https://api.elevenlabs.io/v1/user', {
          headers: {
            'xi-api-key': config.eleven_labs.api_key
          }
        });
        elevenLabsStatus.status = elevenLabsResponse.ok ? 'healthy' : 'unhealthy';
        elevenLabsStatus.statusCode = elevenLabsResponse.status;
      } catch (error: any) {
        elevenLabsStatus.status = 'unhealthy';
        elevenLabsStatus.error = error.message;
      }
    } else {
      elevenLabsStatus.status = 'disabled';
    }

    const health = {
      uptime: process.uptime(),
      timestamp: Date.now(),
      services: {
        ollama: ollamaStatus,
        chroma: chromaStatus,
        elevenlabs: elevenLabsStatus
      }
    };
    
    const allServicesHealthy = 
      ollamaStatus.status === 'healthy' && 
      chromaStatus.status === 'healthy' && 
      (elevenLabsStatus.status === 'healthy' || elevenLabsStatus.status === 'disabled');
    
    const status = allServicesHealthy ? 200 : 503;
    res.status(status).json(health);
  } catch (error: any) {
    res.status(500).json({
      status: 'error',
      error: error.message
    });
  }
});

// Start the server and store the reference
const server = app.listen(port, () => {
  console.log(`Server running at http://localhost:${port}`);
});

// Implement graceful shutdown
process.on('SIGTERM', gracefulShutdown);
process.on('SIGINT', gracefulShutdown);

async function gracefulShutdown() {
  console.log('Shutdown signal received, closing server gracefully');
  
  // Stop accepting new requests
  server.close(() => {
    console.log('HTTP server closed');
  });
  
  // Wait for existing requests to complete (with timeout)
  const timeout = setTimeout(() => {
    console.log('Forcing shutdown after timeout');
    process.exit(1);
  }, 30000);
  
  try {
    // Clean up resources
    console.log('Cleaning up resources...');
    
    // Close any open connections or resources
    // This is where you would close database connections, etc.
    
    clearTimeout(timeout);
    console.log('Graceful shutdown completed');
    process.exit(0);
  } catch (err) {
    console.error('Error during shutdown:', err);
    process.exit(1);
  }
}