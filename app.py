import os
import requests
from dotenv import load_dotenv
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
import gradio as gr

load_dotenv()  # loads .env file if present — ignored if file doesn't exist

# --- Provider config ---
# Set PROVIDER env var to switch between backends:
#   hf       = HuggingFace transformers (default, no extra install)
#   ollama   = local Ollama server (install from https://ollama.com)
#   groq     = Groq free API (set GROQ_API_KEY env var)
PROVIDER = os.getenv("PROVIDER", "hf")
MODEL_NAME = os.getenv("MODEL_NAME", "TinyLlama/TinyLlama-1.1B-Chat-v1.0")
MAX_NEW_TOKENS = int(os.getenv("MAX_NEW_TOKENS", "200"))
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")

# Load HF pipeline only if using HF provider
hf_gen = None
if PROVIDER == "hf":
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForCausalLM.from_pretrained(MODEL_NAME)
    hf_gen = pipeline(
        "text-generation",
        model=model,
        tokenizer=tokenizer,
        device=-1,
        pad_token_id=tokenizer.eos_token_id  # suppresses pad_token warning
    )


# Gradio 6.x uses messages format: list of {"role": "user"|"assistant", "content": str}
History = list[dict]


def build_prompt(history: History, user_message: str) -> str:
    # TinyLlama chat template: <|system|>\n<|user|>\n<|assistant|>
    prompt = "<|system|>\nYou are a helpful assistant.\n"
    for msg in history[-8:]:  # last 8 messages = 4 turns
        tag = "<|user|>" if msg["role"] == "user" else "<|assistant|>"
        prompt += f"{tag}\n{msg['content']}\n"
    prompt += f"<|user|>\n{user_message}\n<|assistant|>\n"
    return prompt


def _call_hf(prompt: str) -> str:
    output = hf_gen(
        prompt,
        max_new_tokens=MAX_NEW_TOKENS,
        do_sample=True,
        temperature=0.7,
        repetition_penalty=1.1,
        return_full_text=False  # returns only the generated part, no need to slice
    )[0]["generated_text"]
    reply = output.strip()
    reply = reply.split("<|user|>")[0].strip()
    return reply or "I'm not sure, could you rephrase that?"


def _call_ollama(prompt: str) -> str:
    response = requests.post(
        OLLAMA_URL,
        json={"model": MODEL_NAME, "prompt": prompt, "stream": False},
        timeout=60
    )
    return response.json().get("response", "").strip()


def _call_groq(history: History, user_message: str) -> str:
    from groq import Groq
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    messages = [{"role": "system", "content": "You are a helpful assistant."}]
    for msg in history[-8:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_message})
    response = client.chat.completions.create(model=MODEL_NAME or "llama3-8b-8192", messages=messages)
    return response.choices[0].message.content


def chat(user_message: str, history: History) -> tuple[str, History]:
    if PROVIDER == "hf":
        prompt = build_prompt(history, user_message)
        reply = _call_hf(prompt)
    elif PROVIDER == "ollama":
        prompt = build_prompt(history, user_message)
        reply = _call_ollama(prompt)
    elif PROVIDER == "groq":
        reply = _call_groq(history, user_message)
    else:
        reply = f"Unknown provider: {PROVIDER}. Set PROVIDER to hf, ollama, or groq."

    reply = reply or "I'm not sure, could you rephrase that?"
    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": reply})
    return "", history


with gr.Blocks(title="CloudToAILearn — Week 1: Simple Chat") as demo:
    gr.Markdown(
        f"## 🤖 Simple Local Chat — Week 1\n"
        f"Provider: `{PROVIDER}` | Model: `{MODEL_NAME}` | "
        "Part of the [cloudtoailearn.dev](https://cloudtoailearn.dev/) demo series."
    )
    chatbot = gr.Chatbot(label="Chat", height=400)
    txt = gr.Textbox(placeholder="Ask me anything...", show_label=False)
    with gr.Row():
        send_btn = gr.Button("Send", variant="primary")
        clear_btn = gr.Button("Clear")

    send_btn.click(chat, inputs=[txt, chatbot], outputs=[txt, chatbot])
    txt.submit(chat, inputs=[txt, chatbot], outputs=[txt, chatbot])
    clear_btn.click(lambda: ([], ""), outputs=[chatbot, txt])

    gr.Markdown(
        "---\n"
        "⚠️ **Disclaimer:** This is a demo using a small CPU model. "
        "Outputs may be inaccurate. Not for production use. See `DISCLAIMER.md`."
    )

if __name__ == "__main__":
    demo.launch(server_name="127.0.0.1", server_port=7860, show_error=True)
