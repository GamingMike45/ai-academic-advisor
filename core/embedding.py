from pathlib import Path
from sentence_transformers import SentenceTransformer
from chromadb import EmbeddingFunction, Documents, Embeddings
import chromadb, json, requests, csv
import re
import sys  
import os

class EmbeddingGemma300m(EmbeddingFunction):
    def __init__(self, path=os.path.join(os.path.dirname(__file__), "vault", "embeddinggemma-300m")):
        self.model = SentenceTransformer(path)
    
    def __call__(self, input: Documents) -> Embeddings:
        return self.model.encode(input)
