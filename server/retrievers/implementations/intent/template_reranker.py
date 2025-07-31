"""
Template reranking system for Intent retriever using domain-specific rules
"""

import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


class TemplateReranker:
    """Rerank templates using domain-specific rules and vocabulary"""
    
    def __init__(self, domain_config: Optional[Dict[str, Any]] = None):
        self.domain_config = domain_config or {}
    
    def rerank_templates(self, templates: List[Dict], user_query: str) -> List[Dict]:
        """Rerank templates using domain-specific rules"""
        query_lower = user_query.lower()
        
        for template_info in templates:
            template = template_info['template']
            boost = 0.0
            
            # Special handling for person names vs cities
            template_id = template.get('id', '')
            if 'customer_name' in template_id:
                # Check if query likely contains a person name
                if self._contains_person_name_pattern(query_lower):
                    boost += 0.3
            elif 'customer_city' in template_id:
                # Check if query likely contains a city name
                if self._contains_city_pattern(query_lower):
                    boost += 0.3
                # Penalize if it looks like a person name
                if self._contains_person_name_pattern(query_lower):
                    boost -= 0.2
            
            # Check for entity matches using domain vocabulary
            semantic_tags = template.get('semantic_tags', {})
            if semantic_tags:
                primary_entity = semantic_tags.get('primary_entity')
                if primary_entity:
                    boost += self._calculate_entity_boost(query_lower, primary_entity)
                
                # Check for action verb matches
                action = semantic_tags.get('action')
                if action:
                    boost += self._calculate_action_boost(query_lower, action)
                
                # Check for qualifier matches
                qualifiers = semantic_tags.get('qualifiers', [])
                for qualifier in qualifiers:
                    if qualifier.lower() in query_lower:
                        boost += 0.1
            
            # Check for tag matches
            tags = template.get('tags', [])
            for tag in tags:
                if tag.lower() in query_lower:
                    boost += 0.05
            
            # Check for natural language example matches
            nl_examples = template.get('nl_examples', [])
            for example in nl_examples:
                similarity = self._calculate_text_similarity(query_lower, example.lower())
                if similarity > 0.5:
                    boost += similarity * 0.2
            
            # Apply boost
            original_similarity = template_info['similarity']
            template_info['similarity'] = min(1.0, original_similarity + boost)
            template_info['boost_applied'] = boost
            
            if boost > 0:
                logger.debug(f"Template {template.get('id')} boosted by {boost:.3f} (original: {original_similarity:.3f}, new: {template_info['similarity']:.3f})")
        
        # Re-sort by adjusted similarity
        return sorted(templates, key=lambda x: x['similarity'], reverse=True)
    
    def _calculate_entity_boost(self, query_lower: str, primary_entity: str) -> float:
        """Calculate boost for entity matches"""
        boost = 0.0
        vocabulary = self.domain_config.get('vocabulary', {})
        entity_synonyms = vocabulary.get('entity_synonyms', {})
        
        # Check primary entity name
        if primary_entity.lower() in query_lower:
            boost += 0.2
        
        # Check entity synonyms
        synonyms = entity_synonyms.get(primary_entity, [])
        for synonym in synonyms:
            if synonym.lower() in query_lower:
                boost += 0.15
                break  # Don't double count
        
        return boost
    
    def _calculate_action_boost(self, query_lower: str, action: str) -> float:
        """Calculate boost for action verb matches"""
        boost = 0.0
        vocabulary = self.domain_config.get('vocabulary', {})
        action_verbs = vocabulary.get('action_verbs', {})
        
        # Check if action or its synonyms are in query
        verbs = action_verbs.get(action, [])
        verbs.append(action)  # Include the action itself
        
        for verb in verbs:
            if verb.lower() in query_lower:
                boost += 0.15
                break  # Don't double count
        
        return boost
    
    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """Calculate simple text similarity between two strings"""
        words1 = set(text1.split())
        words2 = set(text2.split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0
    
    def explain_ranking(self, templates: List[Dict]) -> str:
        """Generate explanation of template ranking for debugging"""
        lines = ["Template Ranking Explanation:", "=" * 30]
        
        for i, template_info in enumerate(templates[:5]):  # Top 5
            template = template_info['template']
            similarity = template_info['similarity']
            boost = template_info.get('boost_applied', 0.0)
            original = similarity - boost
            
            lines.append(f"{i+1}. {template.get('id', 'Unknown')} (similarity: {similarity:.3f})")
            lines.append(f"   Original: {original:.3f}, Boost: +{boost:.3f}")
            lines.append(f"   Description: {template.get('description', 'N/A')}")
            
            semantic_tags = template.get('semantic_tags', {})
            if semantic_tags:
                lines.append(f"   Entity: {semantic_tags.get('primary_entity', 'N/A')}")
                lines.append(f"   Action: {semantic_tags.get('action', 'N/A')}")
            
            lines.append("")
        
        return "\\n".join(lines)
    
    def _contains_person_name_pattern(self, text: str) -> bool:
        """Check if text likely contains a person name"""
        # Common patterns for person names
        words = text.split()
        
        # Check for capitalized words (typical of names)
        # Note: this is checking the lowercase version, so we need to look for patterns
        
        # Check for common name indicators
        person_indicators = [
            'customer', 'person', 'user', 'client', 'buyer',
            'mr', 'mrs', 'ms', 'dr', 'prof'
        ]
        
        for indicator in person_indicators:
            if indicator in text:
                return True
        
        # Check if it contains two consecutive words that could be first/last name
        # Look for patterns like "from [Name] [Name]" or "[Name] [Name] order"
        import re
        
        # Pattern: "from" followed by two capitalized words (checking original case would be better)
        if re.search(r'from\s+\w+\s+\w+', text):
            # If the pattern is "from X Y" where X and Y are words, likely a person
            if not any(city_word in text for city_word in ['city', 'in', 'located', 'from the']):
                return True
        
        # Check for possessive patterns like "angela's orders" or "john's purchases"
        if re.search(r"\w+'s\s+(order|purchase|transaction)", text):
            return True
        
        return False
    
    def _contains_city_pattern(self, text: str) -> bool:
        """Check if text likely contains a city name"""
        # City indicators
        city_indicators = [
            'city', 'location', 'from the', 'in ', 'located in',
            'customers in', 'customers from', 'from customers in'
        ]
        
        for indicator in city_indicators:
            if indicator in text:
                return True
        
        # Check for known geographic qualifiers
        geo_terms = ['downtown', 'north', 'south', 'east', 'west', 'metro', 'greater']
        for term in geo_terms:
            if term in text:
                return True
        
        return False