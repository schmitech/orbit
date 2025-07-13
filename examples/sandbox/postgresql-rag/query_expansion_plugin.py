#!/usr/bin/env python3
"""
Query Expansion Plugin for RAG System
=====================================

This plugin enhances query matching by generating variations and synonyms
using sentence transformers and NLP techniques.
"""

import logging
from typing import List, Dict, Any, Optional
import numpy as np
import re

from plugin_system import BaseRAGPlugin, PluginContext, PluginPriority

logger = logging.getLogger(__name__)


class QueryExpansionPlugin(BaseRAGPlugin):
    """Plugin for expanding queries with variations and synonyms"""
    
    def __init__(self, 
                 enable_sentence_transformers: bool = True,
                 enable_synonyms: bool = True,
                 max_variations: int = 5,
                 similarity_threshold: float = 0.7):
        super().__init__("QueryExpansion", "1.0.0", PluginPriority.HIGH)
        
        self.enable_sentence_transformers = enable_sentence_transformers
        self.enable_synonyms = enable_synonyms
        self.max_variations = max_variations
        self.similarity_threshold = similarity_threshold
        
        # Lazy loading of heavy dependencies
        self._sentence_transformer = None
        self._t5_model = None
        self._t5_tokenizer = None
        self._wordnet = None
        self._nltk_data_loaded = False
        
        # Common business synonyms
        self.business_synonyms = {
            'customer': ['client', 'buyer', 'purchaser', 'user', 'account'],
            'order': ['purchase', 'transaction', 'sale', 'buy', 'acquisition'],
            'show': ['display', 'list', 'find', 'get', 'retrieve', 'pull up'],
            'find': ['search', 'locate', 'discover', 'get', 'show'],
            'recent': ['latest', 'new', 'fresh', 'current', 'latest'],
            'high': ['large', 'big', 'expensive', 'premium', 'valuable'],
            'low': ['small', 'cheap', 'inexpensive', 'budget', 'affordable'],
            'pending': ['waiting', 'processing', 'in progress', 'not completed'],
            'completed': ['finished', 'done', 'fulfilled', 'delivered'],
            'total': ['amount', 'sum', 'value', 'cost', 'price'],
            'payment': ['pay', 'transaction', 'billing', 'charge'],
            'method': ['type', 'way', 'form', 'option', 'means']
        }
    
    def _load_sentence_transformer(self):
        """Lazy load sentence transformer"""
        if self._sentence_transformer is None and self.enable_sentence_transformers:
            try:
                from sentence_transformers import SentenceTransformer
                self._sentence_transformer = SentenceTransformer('all-MiniLM-L6-v2')
                logger.info("Loaded sentence transformer model")
            except ImportError:
                logger.warning("sentence-transformers not available. Install with: pip install sentence-transformers")
                self.enable_sentence_transformers = False
    
    def _load_t5_model(self):
        """Lazy load T5 model for paraphrasing"""
        if self._t5_model is None and self.enable_sentence_transformers:
            try:
                from transformers import T5ForConditionalGeneration, T5Tokenizer
                self._t5_model = T5ForConditionalGeneration.from_pretrained('t5-base')
                self._t5_tokenizer = T5Tokenizer.from_pretrained('t5-base')
                logger.info("Loaded T5 model for paraphrasing")
            except ImportError:
                logger.warning("transformers not available. Install with: pip install transformers")
                self.enable_sentence_transformers = False
    
    def _load_nltk_data(self):
        """Lazy load NLTK data"""
        if not self._nltk_data_loaded and self.enable_synonyms:
            try:
                import nltk
                # Download required NLTK data
                try:
                    nltk.data.find('tokenizers/punkt')
                except LookupError:
                    nltk.download('punkt')
                
                try:
                    nltk.data.find('corpora/wordnet')
                except LookupError:
                    nltk.download('wordnet')
                
                self._wordnet = nltk.corpus.wordnet
                self._nltk_data_loaded = True
                logger.info("Loaded NLTK data for synonyms")
            except ImportError:
                logger.warning("NLTK not available. Install with: pip install nltk")
                self.enable_synonyms = False
    
    def pre_process_query(self, query: str, context: PluginContext) -> str:
        """Expand query with variations before processing"""
        if not self.is_enabled():
            return query
        
        # Load dependencies if needed
        self._load_sentence_transformer()
        self._load_nltk_data()
        
        # Store original query
        context.original_query = query
        
        # Generate variations
        variations = self._generate_query_variations(query)
        
        if variations:
            # Store variations in context for later use
            context.query_variations = variations
            logger.debug(f"Generated {len(variations)} query variations")
            
            # For now, return the original query but with variations available
            # The template matching will use these variations
            return query
        
        return query
    
    def _generate_query_variations(self, query: str) -> List[str]:
        """Generate query variations using multiple techniques"""
        variations = [query]  # Always include original
        
        # 1. Business synonym expansion
        if self.enable_synonyms:
            synonym_variations = self._expand_with_business_synonyms(query)
            variations.extend(synonym_variations)
        
        # 2. NLTK WordNet synonyms
        if self.enable_synonyms and self._wordnet:
            wordnet_variations = self._expand_with_wordnet(query)
            variations.extend(wordnet_variations)
        
        # 3. T5 paraphrasing
        if self.enable_sentence_transformers and self._t5_model:
            paraphrase_variations = self._generate_paraphrases(query)
            variations.extend(paraphrase_variations)
        
        # Remove duplicates and limit
        unique_variations = list(dict.fromkeys(variations))  # Preserve order
        return unique_variations[:self.max_variations]
    
    def _expand_with_business_synonyms(self, query: str) -> List[str]:
        """Expand query using business-specific synonyms"""
        variations = []
        query_lower = query.lower()
        
        for word, synonyms in self.business_synonyms.items():
            if word in query_lower:
                for synonym in synonyms:
                    # Simple replacement (case-insensitive)
                    pattern = re.compile(re.escape(word), re.IGNORECASE)
                    variation = pattern.sub(synonym, query)
                    if variation != query:
                        variations.append(variation)
        
        return variations
    
    def _expand_with_wordnet(self, query: str) -> List[str]:
        """Expand query using WordNet synonyms"""
        if not self._wordnet:
            return []
        
        try:
            import nltk
            variations = []
            tokens = nltk.word_tokenize(query)
            
            for i, token in enumerate(tokens):
                # Get synonyms for the token
                synonyms = []
                for syn in self._wordnet.synsets(token):
                    for lemma in syn.lemmas():
                        if lemma.name() != token and len(lemma.name()) > 2:  # Avoid very short words
                            synonyms.append(lemma.name())
                
                # Create variations with synonyms (limit to avoid explosion)
                for synonym in synonyms[:2]:
                    new_tokens = tokens.copy()
                    new_tokens[i] = synonym
                    variation = ' '.join(new_tokens)
                    if variation != query:
                        variations.append(variation)
            
            return variations
        except Exception as e:
            logger.warning(f"Error expanding with WordNet: {e}")
            return []
    
    def _generate_paraphrases(self, query: str) -> List[str]:
        """Generate paraphrases using T5 model"""
        if not self._t5_model or not self._t5_tokenizer:
            return []
        
        try:
            # Prepare input
            input_text = f"paraphrase: {query}"
            inputs = self._t5_tokenizer(input_text, return_tensors="pt", max_length=50, truncation=True)
            
            # Generate paraphrases
            outputs = self._t5_model.generate(
                **inputs,
                max_length=50,
                num_return_sequences=2,
                num_beams=5,
                temperature=0.8,
                do_sample=True,
                pad_token_id=self._t5_tokenizer.eos_token_id
            )
            
            variations = []
            for output in outputs:
                paraphrase = self._t5_tokenizer.decode(output, skip_special_tokens=True)
                if paraphrase and paraphrase != query and len(paraphrase) > 10:
                    variations.append(paraphrase)
            
            return variations
        except Exception as e:
            logger.warning(f"Error generating paraphrases: {e}")
            return []
    
    def enhance_template_matching(self, templates: List[Dict], query: str, context: PluginContext) -> List[Dict]:
        """Enhance template matching using query variations"""
        if not self.is_enabled() or not hasattr(context, 'query_variations'):
            return templates
        
        enhanced_templates = []
        
        for template_info in templates:
            template = template_info['template']
            original_similarity = template_info['similarity']
            
            # Test variations against this template
            best_similarity = original_similarity
            
            for variation in context.query_variations:
                if variation != query:  # Skip original query
                    # Calculate similarity for variation
                    variation_similarity = self._calculate_similarity(variation, template)
                    
                    if variation_similarity > best_similarity:
                        best_similarity = variation_similarity
                        logger.debug(f"Template {template['id']}: {original_similarity:.3f} -> {best_similarity:.3f} (via: {variation[:30]}...)")
            
            # Update template info with enhanced similarity
            enhanced_template_info = template_info.copy()
            enhanced_template_info['similarity'] = best_similarity
            enhanced_template_info['query_expansion_boost'] = best_similarity - original_similarity
            
            enhanced_templates.append(enhanced_template_info)
        
        # Re-sort by enhanced similarity
        enhanced_templates.sort(key=lambda x: x['similarity'], reverse=True)
        
        return enhanced_templates
    
    def _calculate_similarity(self, query: str, template: Dict) -> float:
        """Calculate similarity between query and template"""
        if not self._sentence_transformer:
            return 0.0
        
        try:
            # Get embeddings
            query_embedding = self._sentence_transformer.encode([query])[0]
            
            # Create template text from examples and tags
            template_text = ' '.join(template.get('nl_examples', []) + template.get('tags', []))
            template_embedding = self._sentence_transformer.encode([template_text])[0]
            
            # Calculate cosine similarity
            similarity = np.dot(query_embedding, template_embedding) / (
                np.linalg.norm(query_embedding) * np.linalg.norm(template_embedding)
            )
            
            return float(similarity)
        except Exception as e:
            logger.warning(f"Error calculating similarity: {e}")
            return 0.0
    
    def post_process_results(self, results: List[Dict], context: PluginContext) -> List[Dict]:
        """Add query expansion metadata to results"""
        if not self.is_enabled():
            return results
        
        # Add expansion metadata to context
        if hasattr(context, 'query_variations'):
            context.expansion_metadata = {
                'original_query': getattr(context, 'original_query', ''),
                'variations_generated': len(context.query_variations),
                'variations': context.query_variations[:3]  # Show first 3
            }
        
        return results
    
    def enhance_response(self, response: str, context: PluginContext) -> str:
        """Add query expansion information to response"""
        if not self.is_enabled() or not hasattr(context, 'expansion_metadata'):
            return response
        
        metadata = context.expansion_metadata
        
        # Add expansion info if it helped
        if metadata.get('variations_generated', 0) > 1:
            expansion_info = f"\n\n💡 *Query expanded with {metadata['variations_generated']} variations to improve matching*"
            response += expansion_info
        
        return response


# Example usage and testing
def test_query_expansion():
    """Test the query expansion plugin"""
    plugin = QueryExpansionPlugin(
        enable_sentence_transformers=True,
        enable_synonyms=True,
        max_variations=5
    )
    
    # Test query
    test_query = "Show me orders from Maria Smith"
    print(f"Original query: {test_query}")
    
    # Create context
    context = PluginContext(user_query=test_query)
    
    # Test pre-processing
    processed_query = plugin.pre_process_query(test_query, context)
    print(f"Processed query: {processed_query}")
    
    if hasattr(context, 'query_variations'):
        print(f"\nGenerated variations:")
        for i, variation in enumerate(context.query_variations, 1):
            print(f"  {i}. {variation}")
    
    # Test template matching enhancement
    sample_template = {
        'id': 'customer_orders_by_name',
        'nl_examples': ['Show me orders from Maria Smith', 'Find orders for John Doe'],
        'tags': ['customer', 'orders', 'name']
    }
    
    templates = [{'template': sample_template, 'similarity': 0.6}]
    enhanced = plugin.enhance_template_matching(templates, test_query, context)
    
    print(f"\nTemplate matching enhancement:")
    for template_info in enhanced:
        boost = template_info.get('query_expansion_boost', 0)
        print(f"  Similarity: {template_info['similarity']:.3f} (boost: {boost:.3f})")


if __name__ == "__main__":
    test_query_expansion() 