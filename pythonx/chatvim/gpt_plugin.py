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
    def gpt_response(self):
        history, last_talked = self._get_chat_history()
        if len(history) > 0:
            response = self._get_gpt_response(history, last_talked)
            self._insert_response(response)

    def _get_gpt_response(self, history, last_talked):
        model = self.nvim.vars.get("gpt_model", "gpt-3.5-turbo")

        # last_talked overrides global variable
        if last_talked == "3":
            model = "gpt-3.5-turbo"
        elif last_talked == "4":
            model = "gpt-4"

        system_prompt = []

        result = openai.ChatCompletion.create(
            model=model,
            messages=system_prompt + history ,
        )

        response = result['choices'][0]['message']['content']
        return response

    def _get_chat_history(self):
        cursor_line, _ = self.nvim.current.window.cursor
        lines = self.nvim.current.buffer[:cursor_line]
        history = []
        last_talked = None

        for line in lines:
            if line.startswith("//") or line.startswith("#"):
                continue
            if line.startswith("GPT:"):
                history.append({"role": "assistant", "content": line[4:].strip()})
            elif line.startswith(">") or line.startswith("3>") or line.startswith("4>"):
                if line.startswith(">>") or line.startswith("3>>") or line.startswith("4>>"):
                    history = []
                    history.append({"role": "user", "content": line[2:].strip()})
                else:
                    history.append({"role": "user", "content": line[1:].strip()})
                if line.startswith("3"):
                    last_talked = "3"
                elif line.startswith("4"):
                    last_talked = "4"
                else:
                    last_talked = None
            else:
                if len(history) > 0:
                    history[-1]["content"] += "\n" + line.strip()
        return history, last_talked

    def _insert_response(self, response):
        self.nvim.command("setlocal paste")
        self.nvim.command("normal! oGPT: {}".format(response))
        self.nvim.command("normal! o>")
        self.nvim.command("setlocal nopaste")

