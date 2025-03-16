import fitz  # PyMuPDF
import os
import re
import json
import requests

# 📂 Path to PDF directory
PDF_FOLDER = "pdfs/"

# ✅ Groq API Config
GROQ_API_KEY = "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"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# 📌 Regex pattern to detect Arabic words
arabic_word_pattern = re.compile(r"[\u0600-\u06FF]+")

def search_word_in_pdfs(word):
    """
    Searches for a Hassaniya word inside PDFs and extracts its definition, grammatical forms, and examples.
    """
    for filename in os.listdir(PDF_FOLDER):
        if filename.endswith(".pdf"):
            pdf_path = os.path.join(PDF_FOLDER, filename)
            doc = fitz.open(pdf_path)

            for page in doc:
                text = page.get_text("text")
                lines = text.split("\n")

                for i, line in enumerate(lines):
                    words = line.split()
                    if words and words[0] == word:
                        # ✅ Found the word → Extract explanation
                        definition = " ".join(words[1:])
                        
                        # ✅ Get next lines to capture variants/conjugations
                        variants = []
                        for j in range(i + 1, min(i + 5, len(lines))):
                            if not arabic_word_pattern.match(lines[j].split()[0]):  # Stop if next line isn't Arabic
                                break
                            variants.append(lines[j])

                        return {
                            "word": word,
                            "definition": definition,
                            "variants": variants
                        }
    
    return None  # ❌ Word not found

def generate_definition(word):
    """
    Uses Groq AI to generate a definition, variants, and example sentences for a missing Hassaniya word.
    """
    if not GROQ_API_KEY:
        return "L'IA n'est pas disponible (clé API manquante)."

    payload = {
        "model": "llama3-70b-8192",
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": """
            Vous êtes un expert en linguistique et dialectologie du Hassaniya arabe.  
            Répondez uniquement en **français**.

            ✅ **Si le mot existe**, fournissez :  
            - **Définition précise en français**  
            - **Origine du mot (arabe, berbère, français, etc.)**  
            - **Exemple de phrase en Hassaniya avec transcription latine et traduction**  
            - **Variantes du mot, si elles existent**  

            ❌ **Si vous ne connaissez pas le mot, répondez uniquement:**  
            `"Je ne connais pas ce mot. Pouvez-vous me l'expliquer ?"`
            """},
            {"role": "user", "content": f"Définir le mot: {word}"}
        ]
    }

    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    response = requests.post(GROQ_URL, json=payload, headers=headers)

    if response.status_code == 200:
        return response.json()["choices"][0]["message"]["content"].strip()
    return "Définition indisponible."


def generate_variants(word):
    """Uses Groq AI to generate variants (conjugations, grammatical forms) for the given word."""
    if not GROQ_API_KEY:
        return ["L'IA n'est pas disponible (clé API manquante)."]

    payload = {
        "model": "llama3-70b-8192",
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": """
            Vous êtes un expert en linguistique Hassaniya.
            Votre tâche est de générer 3 a 4  variantes d'un mot donné.
            Incluez la conjugaison, les formes grammaticales et les dérivations.
            Répondez sous forme de liste JSON.
            """},
            {"role": "user", "content": f"Génère des variantes pour le mot: {word}"}
        ]
    }

    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    
    try:
        response = requests.post(GROQ_URL, json=payload, headers=headers)
        
        if response.status_code == 200:
            ai_response = response.json()["choices"][0]["message"]["content"]
            
            # Handle possible JSON within markdown code blocks
            if "```json" in ai_response:
                # Extract JSON from markdown code block
                start_idx = ai_response.find("```json") + 7
                end_idx = ai_response.find("```", start_idx)
                json_content = ai_response[start_idx:end_idx].strip()
                return json.loads(json_content)
            
            # Try direct JSON parsing
            try:
                return json.loads(ai_response)
            except json.JSONDecodeError:
                # If it's not valid JSON, return as a single item list
                return [ai_response]
                
        # Handle API error
        return [f"Erreur API: {response.status_code}"]
        
    except Exception as e:
        # Safely handle any errors
        return [f"Erreur lors de la génération des variantes: {str(e)}"]