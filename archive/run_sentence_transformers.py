#!/usr/bin/env python3.10
"""Run sentence-transformers with Python 3.10."""

import sys
sys.path.insert(0, '/home/runner/.pythonlibs/lib/python3.10/site-packages')

import json
import numpy as np
from sentence_transformers import SentenceTransformer, util

def main():
    # Get input from command line
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Usage: run_sentence_transformers.py <command> <args>"}))
        return
    
    command = sys.argv[1]
    
    try:
        # Initialize model
        model = SentenceTransformer('all-MiniLM-L6-v2')
        
        if command == "encode":
            # Encode texts
            texts = json.loads(sys.argv[2])
            embeddings = model.encode(texts, convert_to_numpy=True)
            # Convert to list for JSON serialization
            result = {"embeddings": embeddings.tolist()}
            
        elif command == "similarity":
            # Calculate similarity between two texts
            text1 = sys.argv[2]
            text2 = sys.argv[3]
            embeddings = model.encode([text1, text2])
            similarity = util.cos_sim(embeddings[0], embeddings[1]).item()
            result = {"similarity": similarity}
            
        elif command == "search":
            # Semantic search
            query = sys.argv[2]
            corpus = json.loads(sys.argv[3])
            
            # Encode query and corpus
            query_embedding = model.encode(query, convert_to_numpy=True)
            corpus_embeddings = model.encode(corpus, convert_to_numpy=True)
            
            # Calculate similarities
            cos_scores = util.cos_sim(query_embedding, corpus_embeddings)[0]
            
            # Get top results
            top_k = min(10, len(corpus))
            import torch
            top_results = torch.topk(cos_scores, k=top_k)
            
            results = []
            for score, idx in zip(top_results[0], top_results[1]):
                results.append({
                    "index": int(idx),
                    "text": corpus[idx],
                    "score": float(score)
                })
            
            result = {"results": results}
        
        else:
            result = {"error": f"Unknown command: {command}"}
        
        print(json.dumps(result))
        
    except Exception as e:
        print(json.dumps({"error": str(e)}))

if __name__ == "__main__":
    main()