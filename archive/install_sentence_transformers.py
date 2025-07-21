"""Install and use sentence-transformers directly."""

import subprocess
import sys
import os

# Create a separate environment for sentence-transformers
try:
    # First, try to import it
    from sentence_transformers import SentenceTransformer
    print("✓ sentence-transformers is already installed!")
except ImportError:
    print("Installing sentence-transformers...")
    try:
        # Install directly with pip
        subprocess.check_call([sys.executable, "-m", "pip", "install", 
                              "sentence-transformers==3.2.0", 
                              "--no-deps"])
        
        # Install core dependencies
        subprocess.check_call([sys.executable, "-m", "pip", "install",
                              "transformers>=4.41.0",
                              "torch>=1.11.0",
                              "numpy",
                              "scikit-learn",
                              "scipy",
                              "nltk",
                              "tqdm",
                              "huggingface-hub"])
        
        print("✓ Successfully installed sentence-transformers!")
        
        # Test import
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer('all-MiniLM-L6-v2')
        print("✓ Successfully loaded a test model!")
        
    except Exception as e:
        print(f"Failed to install: {e}")
        print("Trying alternative installation method...")
        
        # Try with minimal dependencies
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install",
                                  "sentence-transformers", "--user", "--no-deps"])
            print("✓ Installed with --user flag")
        except:
            print("✗ Could not install sentence-transformers")