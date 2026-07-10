"""
ByrdHouse RAG - Retrieval Augmented Generation System
Loads documents on-demand, finds relevant content, augments AI responses
"""
import os
import json
import hashlib
import time
from datetime import datetime

class RAGSystem:
    def __init__(self, docs_path=None, index_path=None):
        self.docs_path = docs_path or r"E:\byrdhouse_rag\documents"
        self.index_path = index_path or r"E:\byrdhouse_rag\index"
        self.chunks = []
        self.vectors = []
        
        os.makedirs(self.docs_path, exist_ok=True)
        os.makedirs(self.index_path, exist_ok=True)
        
        self._load_index()
    
    def _load_index(self):
        """Load existing index."""
        index_file = os.path.join(self.index_path, 'chunks.json')
        if os.path.exists(index_file):
            try:
                with open(index_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.chunks = data.get('chunks', [])
                    self.vectors = data.get('vectors', [])
                print(f"[RAG] Loaded {len(self.chunks)} document chunks")
            except:
                pass
    
    def _save_index(self):
        """Save index to disk."""
        os.makedirs(self.index_path, exist_ok=True)
        index_file = os.path.join(self.index_path, 'chunks.json')
        with open(index_file, 'w', encoding='utf-8') as f:
            json.dump({
                'chunks': self.chunks,
                'vectors': self.vectors,
                'updated': datetime.now().isoformat()
            }, f, ensure_ascii=False)
    
    def _embed_text(self, text):
        """Simple hash-based embedding for quick similarity."""
        # Create a simple numerical representation
        text_hash = hashlib.md5(text.encode()).hexdigest()
        # Convert hex to numbers for vector
        vector = [int(text_hash[i:i+8], 16) % 1000 for i in range(0, 32, 8)]
        return vector
    
    def _cosine_similarity(self, v1, v2):
        """Calculate cosine similarity between two vectors."""
        dot = sum(a * b for a, b in zip(v1, v2))
        mag1 = sum(a * a for a in v1) ** 0.5
        mag2 = sum(b * b for b in v2) ** 0.5
        if mag1 == 0 or mag2 == 0:
            return 0
        return dot / (mag1 * mag2)
    
    def add_document(self, title, content, source="manual"):
        """Add a document to the RAG system."""
        # Split content into chunks
        chunk_size = 500
        words = content.split()
        
        chunks = []
        for i in range(0, len(words), chunk_size):
            chunk_text = ' '.join(words[i:i + chunk_size])
            if chunk_text.strip():
                chunks.append(chunk_text)
        
        # Add each chunk
        for i, chunk in enumerate(chunks):
            chunk_data = {
                'id': len(self.chunks),
                'title': title,
                'content': chunk,
                'source': source,
                'chunk_index': i,
                'added': datetime.now().isoformat()
            }
            vector = self._embed_text(chunk)
            
            self.chunks.append(chunk_data)
            self.vectors.append(vector)
        
        self._save_index()
        print(f"[RAG] Added '{title}' with {len(chunks)} chunks")
        return len(chunks)
    
    def search(self, query, top_k=5):
        """Search for relevant chunks."""
        query_vector = self._embed_text(query)
        
        # Calculate similarities
        results = []
        for i, (chunk, vector) in enumerate(zip(self.chunks, self.vectors)):
            similarity = self._cosine_similarity(query_vector, vector)
            results.append((similarity, chunk))
        
        # Sort by similarity
        results.sort(key=lambda x: x[0], reverse=True)
        
        # Return top results
        return results[:top_k]
    
    def retrieve_context(self, query, max_chars=2000):
        """Retrieve relevant context for a query."""
        results = self.search(query, top_k=5)
        
        context = ""
        for similarity, chunk in results:
            if len(context) + len(chunk['content']) < max_chars:
                context += f"\n\n[Source: {chunk['title']}]\n{chunk['content']}"
        
        return context if context else None
    
    def get_stats(self):
        """Get RAG stats."""
        return {
            'total_chunks': len(self.chunks),
            'sources': list(set(c['source'] for c in self.chunks)),
            'index_size': os.path.getsize(os.path.join(self.index_path, 'chunks.json')) / 1024 if self.chunks else 0
        }


# =================================================================
# BUILT-IN DOCUMENT KNOWLEDGE BASE
# =================================================================
DEFAULT_KNOWLEDGE = [
    {
        "title": "Python Programming Guide",
        "source": "byrdhouse_kb",
        "content": """
Python is a high-level programming language known for its simplicity and readability. 
Key features: list comprehensions, dictionaries, tuple unpacking, virtual environments (venv), pip package manager.
Common frameworks: Flask, Django, FastAPI, NumPy, Pandas, PyTorch.
Best practices: Use type hints, follow PEP 8 style guide, write docstrings, use virtual environments.
Error handling: try/except blocks, custom exceptions, logging module.
Data structures: list, dict, set, tuple - each has specific use cases and performance characteristics.
"""
    },
    {
        "title": "JavaScript & Web Development",
        "source": "byrdhouse_kb",
        "content": """
JavaScript is the language of the web. Modern JS (ES6+) features: arrow functions, template literals, destructuring, spread operator.
Async programming: Promises, async/await, fetch API.
DOM manipulation: querySelector, createElement, addEventListener.
Frameworks: React, Vue, Angular, Next.js, Node.js.
npm is the package manager. package.json manages dependencies.
Common patterns: module.exports, import/export, closures, event delegation.
"""
    },
    {
        "title": "Git Version Control",
        "source": "byrdhouse_kb",
        "content": """
Git is a distributed version control system. Key commands:
git init, git clone, git add, git commit, git push, git pull, git fetch.
Branching: git branch, git checkout, git merge, git rebase.
Stashing: git stash, git stash pop, git stash drop.
Viewing: git log, git diff, git status, git show.
Advanced: git cherry-pick, git reset, git revert, git bisect.
GitHub/GitLab provide remote hosting and collaboration features.
"""
    },
    {
        "title": "SQL & Databases",
        "source": "byrdhouse_kb",
        "content": """
SQL (Structured Query Language) for database management.
Commands: SELECT, INSERT, UPDATE, DELETE, CREATE, DROP.
Joins: INNER, LEFT, RIGHT, FULL OUTER JOIN.
Aggregations: COUNT, SUM, AVG, MIN, MAX with GROUP BY.
Constraints: PRIMARY KEY, FOREIGN KEY, UNIQUE, NOT NULL, CHECK.
Indexing improves query performance. Normalization reduces redundancy.
Popular databases: PostgreSQL, MySQL, SQLite, MongoDB.
"""
    },
    {
        "title": "AI & Machine Learning",
        "source": "byrdhouse_kb",
        "content": """
AI (Artificial Intelligence) enables machines to learn and make decisions.
Machine Learning: Supervised, unsupervised, reinforcement learning.
Deep Learning: Neural networks with many layers, CNNs for images, RNNs for sequences.
Transformers: BERT, GPT models for NLP tasks.
Tools: PyTorch, TensorFlow, scikit-learn, Hugging Face.
Local AI: Ollama, llama.cpp, vLLM for running models on your hardware.
RAG (Retrieval Augmented Generation) combines search with AI for better answers.
"""
    },
    {
        "title": "Docker & Containerization",
        "source": "byrdhouse_kb",
        "content": """
Docker packages applications with their dependencies.
Images: Templates for containers. Docker Hub: image registry.
Commands: docker build, docker run, docker ps, docker stop, docker rm.
Dockerfile: Instructions to build an image. docker-compose.yml for multi-container apps.
Volumes: Persistent data storage outside containers.
Networking: Port mapping, container communication.
Kubernetes: Container orchestration for scaling and management.
"""
    },
    {
        "title": "Linux & Command Line",
        "source": "byrdhouse_kb",
        "content": """
Linux is a Unix-like operating system kernel.
Shell commands: ls, cd, pwd, mkdir, rm, cp, mv, cat, grep, find.
Permissions: chmod, chown, sudo.
Processes: ps, top, kill, bg, fg.
Networking: ping, curl, wget, ssh, scp.
Text processing: awk, sed, sort, uniq, wc.
Package managers: apt, yum, pacman (distro-specific).
"""
    },
    {
        "title": "API Design & REST",
        "source": "byrdhouse_kb",
        "content": """
API (Application Programming Interface) allows software to communicate.
REST (Representational State Transfer) is the most common web API style.
HTTP methods: GET (read), POST (create), PUT/PATCH (update), DELETE (remove).
Status codes: 200 OK, 201 Created, 400 Bad Request, 401 Unauthorized, 404 Not Found, 500 Server Error.
Authentication: API keys, OAuth 2.0, JWT tokens.
Best practices: Use nouns not verbs, versioning, pagination, rate limiting.
"""
    },
    {
        "title": "Security Best Practices",
        "source": "byrdhouse_kb",
        "content": """
Security protects systems from unauthorized access and attacks.
Authentication: Strong passwords, multi-factor authentication, OAuth.
Authorization: Role-based access control (RBAC), principle of least privilege.
Encryption: HTTPS/TLS for transit, AES for storage, bcrypt for passwords.
Input validation: Sanitize all user input to prevent injection attacks.
Common vulnerabilities: SQL injection, XSS, CSRF, buffer overflow.
Regular security audits and updates are essential.
"""
    },
    {
        "title": "System Design & Architecture",
        "source": "byrdhouse_kb",
        "content": """
System design involves planning scalable, reliable software.
Monolith vs Microservices: Monolith is simpler, microservices scale better.
Load balancing: Distributes traffic across servers.
Caching: Redis, Memcached reduce database load.
CDN: Content Delivery Network for faster global delivery.
Database: SQL vs NoSQL, replication, sharding.
Message queues: RabbitMQ, Kafka for async communication.
Microservices communicate via REST, gRPC, or message brokers.
"""
    }
]

def create_rag_system():
    """Create and populate RAG system with default knowledge."""
    rag = RAGSystem()
    
    # Add default knowledge base
    for doc in DEFAULT_KNOWLEDGE:
        rag.add_document(doc['title'], doc['content'], doc['source'])
    
    return rag


# Singleton instance
_rag_instance = None

def get_rag_system():
    global _rag_instance
    if _rag_instance is None:
        _rag_instance = create_rag_system()
    return _rag_instance