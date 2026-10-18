# clinical-deid-es
 TFM del Máster de Desarrollo con IA (BIG school):  Herramienta web que elimina los datos personales de una nota clínica en español antes de usarla con un LLM de terceros. Un modelo propio (RoBERTa clínico fine-tuned con MEDDOCAN) detecta los datos personales; solo los casos dudosos se consultan a un LLM, y solo con la frase afectada.
