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
        if len(history) > 0:
            response = self._get_gpt_response(text, history)
            self._insert_response(response)

    def _get_gpt_response(self, text, history):
        result = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=history + [{"role": "system", "content": text}],
        )

        response = result['choices'][0]['message']['content']
        return response

    def _get_chat_history(self):
        cursor_line, _ = self.nvim.current.window.cursor
        lines = self.nvim.current.buffer[:cursor_line]
        history = []

        for line in lines:
            if line.startswith("GPT:"):
                history.append({"role": "assistant", "content": line[4:].strip()})
            elif line.startswith(">"):
                if line.startswith(">>"):
                    history = []
                    history.append({"role": "user", "content": line[2:].strip()})
                else:
                    history.append({"role": "user", "content": line[1:].strip()})
            else:
                if len(history) > 0:
                    history[-1]["content"] += "\n" + line.strip()
        return history

    def _insert_response(self, response):
        self.nvim.command('setlocal paste')
        self.nvim.command("normal! oGPT: {}".format(response))
        self.nvim.command("normal! o>")
        self.nvim.command('setlocal nopaste')

