import os
import openai
import pynvim

# Set up your OpenAI API key
openai.api_key = os.getenv("OPENAI_API_KEY")

@pynvim.plugin
class GPTPlugin:
    def __init__(self, nvim):
        self.nvim = nvim

    @pynvim.function("GPTResponse")
    def gpt_response(self, args):
        text = args[0]
        history = self._get_chat_history()
        response = self._get_gpt_response(text, history)
        self._insert_response(response)

    def _get_gpt_response(self, text, history):
        result = openai.ChatCompletion.create(
            engine="davinci-codex",
            messages=history + [{"role": "system", "content": text}],
            max_tokens=50,
            n=1,
            stop=None,
            temperature=0.5,
        )

        response = result.choices[0].text.strip()
        return response

    def _get_chat_history(self):
        lines = self.nvim.current.buffer[:]
        history = []

        for line in lines:
            if line.startswith("GPT:"):
                history.append({"role": "assistant", "content": line[4:].strip()})
            elif line.startswith(">"):
                history.append({"role": "user", "content": line[1:].strip()})
        return history

    def _insert_response(self, response):
        self.nvim.command("normal! oGPT: {}".format(response))
        self.nvim.command("normal! o>")

