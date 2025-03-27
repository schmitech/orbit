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
import { Client } from '@elastic/elasticsearch';
import { AppConfig } from './types';
import { VLLMClient } from './vllm';
import dotenv from 'dotenv';
import winston from 'winston';
import 'winston-daily-rotate-file';
import https from 'https';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Load .env file
dotenv.config();

// Replace env vars reset with config loading
// Load config.yaml instead of .env
let config: AppConfig;
try {
  const configPath = path.resolve(__dirname, '../config.yaml');
  console.log('Loading config from:', configPath);
  
  const configFile = await fs.readFile(configPath, 'utf-8');
  config = yaml.load(configFile) as AppConfig;
  
  // Update config with environment variables
  if (process.env.ELASTICSEARCH_USERNAME && process.env.ELASTICSEARCH_PASSWORD) {
    config.elasticsearch.auth = {
      username: process.env.ELASTICSEARCH_USERNAME,
      password: process.env.ELASTICSEARCH_PASSWORD
    };
  }
  
  if (process.env.ELEVEN_LABS_API_KEY) {
    config.eleven_labs.api_key = process.env.ELEVEN_LABS_API_KEY;
  }
  
  if (process.env.HUGGINGFACE_API_KEY) {
    config.huggingface.api_key = process.env.HUGGINGFACE_API_KEY;
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

const port = config.general?.port || 3000;

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
  stream: config.ollama.stream,
  
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
type Backend = 'ollama' | 'hf' | 'vllm';

// Add command line argument parsing
const backend: Backend = process.argv[2] as Backend || 'ollama';
if (!['ollama', 'hf', 'vllm'].includes(backend)) {
  console.error('Invalid backend specified. Use either "ollama", "hf", or "vllm"');
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
const createChain = async (backend: Backend) => {
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
      async (input: string | any) => {
        if (verbose) {
          console.log('\n=== Final Prompt to Ollama ===');
          console.log('Complete Prompt:');
          console.log(input);
          console.log('\nPrompt Length:', typeof input === 'string' ? input.length : JSON.stringify(input).length);
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
  } else if (backend === 'vllm') {
    const vllmClient = new VLLMClient(config, retriever);
    return vllmClient.createChain();
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

// Create and await the chain
const chain = await createChain(backend);

// Initialize Elasticsearch client with better error handling and timeout
const initializeElasticsearch = async () => {
  if (!config.elasticsearch.enabled) {
    return null;
  }

  if (!process.env.ELASTICSEARCH_USERNAME || !process.env.ELASTICSEARCH_PASSWORD) {
    console.warn('Elasticsearch credentials not found in environment variables');
    config.elasticsearch.enabled = false;
    return null;
  }

  try {
    const esClient = new Client({
      node: config.elasticsearch.node,
      auth: {
        username: process.env.ELASTICSEARCH_USERNAME,
        password: process.env.ELASTICSEARCH_PASSWORD
      },
      tls: {
        rejectUnauthorized: false
      },
      requestTimeout: 5000, // 5 second timeout
      pingTimeout: 3000    // 3 second ping timeout
    });

    // Test connection with timeout
    const pingPromise = esClient.ping();
    const timeoutPromise = new Promise((_, reject) => 
      setTimeout(() => reject(new Error('Elasticsearch connection timeout')), 5000)
    );

    await Promise.race([pingPromise, timeoutPromise]);
    console.log('Successfully connected to Elasticsearch');
    return esClient;
  } catch (error: any) {
    console.error('Failed to connect to Elasticsearch:', error.message);
    console.log('Continuing without Elasticsearch logging...');
    config.elasticsearch.enabled = false;
    return null;
  }
};

// Initialize ES client
const esClient = await initializeElasticsearch();

// Initialize logger
const logger = winston.createLogger({
  level: 'info',
  format: winston.format.combine(
    winston.format.timestamp(),
    winston.format.json()
  ),
  transports: [
    new winston.transports.DailyRotateFile({
      filename: path.join(__dirname, '../logs/chat-%DATE%.log'),
      datePattern: 'YYYY-MM-DD',
      maxSize: '20m',
      maxFiles: '14d'
    })
  ]
});

// Add IP formatting utility
interface IPMetadata {
  address: string;
  type: 'ipv4' | 'ipv6' | 'local' | 'unknown';
  isLocal: boolean;
  source: 'direct' | 'proxy' | 'unknown';
  originalValue: string;
}

function formatIPAddress(ip: string | string[] | undefined): IPMetadata {
  // Default metadata
  const metadata: IPMetadata = {
    address: 'unknown',
    type: 'unknown',
    isLocal: false,
    source: 'unknown',
    originalValue: Array.isArray(ip) ? ip.join(', ') : (ip || 'unknown')
  };

  // Handle array from X-Forwarded-For
  const ipToProcess = Array.isArray(ip) ? ip[0] : ip;

  if (!ipToProcess) {
    return metadata;
  }

  // Clean the IP address
  let cleanIP = ipToProcess.trim();

  // Detect and format IPv6 localhost
  if (cleanIP === '::1' || cleanIP === '::ffff:127.0.0.1') {
    return {
      address: 'localhost',
      type: 'local',
      isLocal: true,
      source: 'direct',
      originalValue: cleanIP
    };
  }

  // Detect and format IPv4 localhost
  if (cleanIP === '127.0.0.1' || cleanIP.startsWith('::ffff:127.')) {
    return {
      address: 'localhost',
      type: 'local',
      isLocal: true,
      source: 'direct',
      originalValue: cleanIP
    };
  }

  // Handle IPv4-mapped IPv6 addresses
  if (cleanIP.startsWith('::ffff:')) {
    cleanIP = cleanIP.substring(7);
    metadata.type = 'ipv4';
  } else if (cleanIP.includes(':')) {
    metadata.type = 'ipv6';
  } else {
    metadata.type = 'ipv4';
  }

  metadata.address = cleanIP;
  metadata.isLocal = isLocalIP(cleanIP);
  metadata.source = Array.isArray(ip) ? 'proxy' : 'direct';

  return metadata;
}

function isLocalIP(ip: string): boolean {
  return ip.startsWith('10.') || 
         ip.startsWith('172.16.') || 
         ip.startsWith('192.168.') || 
         ip === '127.0.0.1' || 
         ip === '::1' ||
         ip.startsWith('fc00:') ||
         ip.startsWith('fd') ||
         ip.toLowerCase().startsWith('fe80:');
}

// Modify the logging function to handle both ES and file logging
async function logChatInteraction(data: {
  timestamp: Date;
  query: string;
  response: string;
  backend: 'ollama' | 'hf' | 'vllm';
  blocked?: boolean;
  ip?: string | string[];
}) {
  const ipMetadata = formatIPAddress(data.ip);
  const verbose = config.general?.verbose === 'true';
  
  // Always log to file with full data
  logger.info('Chat Interaction', {
    timestamp: data.timestamp.toISOString(),
    query: data.query,
    response: data.response,
    backend: data.backend,
    blocked: data.blocked || false,
    ip: {
      ...ipMetadata,
      potentialRisk: data.blocked && !ipMetadata.isLocal,
      timestamp: data.timestamp.toISOString()
    },
    elasticsearch_status: config.elasticsearch.enabled ? 'enabled' : 'disabled'
  });

  // Log to Elasticsearch if enabled and available
  if (config.elasticsearch.enabled && esClient) {
    try {
      if (verbose) {
        console.log('\n=== Elasticsearch Logging ===');
        console.log('Attempting to index document to:', config.elasticsearch.index);
      }

      // Convert localhost/friendly names to actual IP for Elasticsearch storage
      const ipForElastic = ipMetadata.type === 'local' ? '127.0.0.1' : ipMetadata.address;

      const document = {
        timestamp: data.timestamp.toISOString(),
        query: data.query,
        response: data.response,
        backend: data.backend,
        blocked: data.blocked || false,
        ip: ipForElastic, // Store actual IP address
        ip_metadata: {
          type: ipMetadata.type,
          isLocal: ipMetadata.isLocal,
          source: ipMetadata.source,
          originalValue: ipMetadata.originalValue,
          potentialRisk: data.blocked && !ipMetadata.isLocal
        }
      };

      if (verbose) {
        console.log('Document to index:', JSON.stringify(document, null, 2));
      }

      const indexResult = await esClient.index({
        index: config.elasticsearch.index,
        document: document,
        refresh: true // This ensures the document is immediately searchable
      });

      if (verbose) {
        console.log('Elasticsearch indexing result:', indexResult);
        
        // Verify document exists
        const verifyDoc = await esClient.get({
          index: config.elasticsearch.index,
          id: indexResult._id
        });
        console.log('Document verification:', verifyDoc);
      }

    } catch (error: any) {
      console.error('Failed to log to Elasticsearch:', { 
        error: error.message,
        stack: error.stack,
        meta: error.meta,
        statusCode: error.statusCode,
        name: error.name
      });
      
      // Try to diagnose the issue
      try {
        const indexExists = await esClient.indices.exists({
          index: config.elasticsearch.index
        });
        
        console.log('Index exists check:', {
          index: config.elasticsearch.index,
          exists: indexExists
        });

        if (!indexExists) {
          console.error('Index does not exist! This should not happen as we create it at startup.');
        }

        const indexSettings = await esClient.indices.get({
          index: config.elasticsearch.index
        });
        
        console.log('Index settings:', indexSettings);
      } catch (diagError: any) {
        console.error('Error during diagnostics:', diagError.message);
      }
    }
  } else if (verbose) {
    console.log('\n=== Elasticsearch Logging Skipped ===');
    console.log('Elasticsearch enabled:', config.elasticsearch.enabled);
    console.log('Elasticsearch client available:', !!esClient);
  }
}

// Update the Elasticsearch mapping
if (config.elasticsearch.enabled && esClient) {
  try {
    await esClient.ping();
    
    // Check if index exists
    const indexExists = await esClient.indices.exists({ index: config.elasticsearch.index });
    if (!indexExists) {
      // Create index with basic settings
      await esClient.indices.create({ 
        index: config.elasticsearch.index,
        body: {
          settings: {
            number_of_shards: 1,
            number_of_replicas: 0
          },
          mappings: {
            properties: {
              timestamp: { type: 'date' },
              query: { type: 'text' },
              response: { type: 'text' },
              backend: { type: 'keyword' },
              blocked: { type: 'boolean' },
              ip: { type: 'ip' },  // Main IP field - will store actual IP
              ip_metadata: {  // Additional IP metadata
                properties: {
                  type: { type: 'keyword' },
                  isLocal: { type: 'boolean' },
                  source: { type: 'keyword' },
                  originalValue: { type: 'keyword' },
                  potentialRisk: { type: 'boolean' }
                }
              }
            }
          }
        }
      });
      console.log(`Created new Elasticsearch index: ${config.elasticsearch.index}`);
    } else {
      console.log(`Using existing Elasticsearch index: ${config.elasticsearch.index}`);
    }
  } catch (error) {
    console.error('Failed to connect to Elasticsearch:', error);
    process.exit(1);
  }
} else if (config.general?.verbose === 'true') {
  console.log('Elasticsearch logging is disabled');
}

// Define guardrail check function
async function checkGuardrail(query: string): Promise<{ safe: boolean }> {
  if (backend === 'vllm') {
    const vllmClient = new VLLMClient(config, retriever);
    return vllmClient.checkGuardrail(query);
  }

  const verbose = config.general?.verbose === 'true';
  
  if (verbose) {
    console.log('\n=== Guardrail Check ===');
    console.log('Query:', query);
  }
  
  try {
    // Create request payload with the guardrail prompt
    const payload = {
      model: config.ollama.model,
      prompt: `${config.system.guardrail_prompt}\n\nQuery: ${query}\n\nRespond with ONLY 'SAFE: true' or 'SAFE: false':`,
      temperature: 0.0,
      top_p: 1.0,
      top_k: 1,
      repeat_penalty: parseFloat(String(config.ollama.repeat_penalty)),
      num_predict: 20,
      stream: false
    };
    
    if (verbose) {
      console.log('\n=== Guardrail Prompt ===');
      console.log(payload.prompt);
    }
    
    // Make request to Ollama
    const response = await fetch(`${config.ollama.base_url}/api/generate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    });
    
    const responseData = await response.json();
    const result = responseData.response?.trim();
    
    if (verbose) {
      console.log('\n=== Guardrail Response ===');
      console.log('Response:', result);
    }
    
    // Check if the response matches the expected format
    if (result === 'SAFE: true') {
      return { safe: true };
    } else if (result === 'SAFE: false') {
      return { safe: false };
    } else {
      console.warn('Guardrail response does not match expected format:', result);
      // Default to safe for non-matching responses, but log the warning
      return { safe: true };
    }
  } catch (error: any) {
    console.error('Error in guardrail check:', error.message);
    // Default to safe on error to prevent complete service failure
    return { safe: true };
  }
}

app.post('/chat', async (req, res) => {
  const startTime = Date.now();
  const { message, voiceEnabled } = req.body;
  
  // Get client IP address
  const ip = req.headers['x-forwarded-for'] || 
             req.socket.remoteAddress || 
             'unknown';

  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');

  try {
    // Add guardrail check before processing the message
    const guardrailResult = await checkGuardrail(message);
    if (!guardrailResult.safe) {
      // Log the blocked query to Elasticsearch
      await logChatInteraction({
        timestamp: new Date(),
        query: message,
        response: 'BLOCKED: Failed guardrail check',
        backend,
        blocked: true,
        ip: typeof ip === 'string' ? ip : ip[0]  // Handle potential array from x-forwarded-for
      });

      // Send the blocked response
      res.write(JSON.stringify({ type: 'text', content: 'Sorry but I cannot help you with that.' }) + '\n');
      res.end();
      return;
    }

    let textBuffer = '';
    let isFirstChunk = true;
    let fullResponse = '';
    
    const stream = await chain.stream({ query: message });
    
    for await (const chunk of stream) {
      if (chunk) {
        fullResponse += chunk;
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
    
    // Log the interaction with IP
    await logChatInteraction({
      timestamp: new Date(),
      query: message,
      response: fullResponse,
      backend,
      ip: typeof ip === 'string' ? ip : ip[0]  // Handle potential array from x-forwarded-for
    });

    res.end();
  } catch (error) {
    console.error('Error:', error);
    
    // Log errors too with IP
    await logChatInteraction({
      timestamp: new Date(),
      query: message,
      response: 'ERROR',
      backend,
      ip: typeof ip === 'string' ? ip : ip[0]  // Handle potential array from x-forwarded-for
    });

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
        'xi-api-key': process.env.ELEVEN_LABS_API_KEY || '',
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
let server: https.Server | ReturnType<typeof app.listen>;
if (config.general?.https?.enabled) {
  try {
    const httpsOptions = {
      key: await fs.readFile(config.general.https.key_file),
      cert: await fs.readFile(config.general.https.cert_file)
    };
    
    server = https.createServer(httpsOptions, app);
    const httpsPort = config.general.https.port || 3443;
    
    server.listen(httpsPort, () => {
      console.log(`HTTPS Server running at https://localhost:${httpsPort}`);
    });
  } catch (error) {
    console.error('Failed to start HTTPS server:', error);
    process.exit(1);
  }
} else {
  server = app.listen(port, () => {
    console.log(`HTTP Server running at http://localhost:${port}`);
  });
}

// Implement graceful shutdown
process.on('SIGTERM', gracefulShutdown);
process.on('SIGINT', gracefulShutdown);

async function gracefulShutdown() {
  console.log('Shutdown signal received, closing server gracefully');
  
  // Stop accepting new requests
  server.close(() => {
    console.log('HTTP/HTTPS server closed');
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