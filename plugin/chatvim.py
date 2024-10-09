import os
import litellm
import pynvim

def line_diff(subseq, line):
    ans = ""
    at = 0
    for c in line:
        if len(subseq) > at and c == subseq[at]:
            at += 1
        else:
            ans += c
    return ans

def get_system_prompt(prompt="default"):
    prompt_dir = os.path.expanduser("~/.config/chatvim/prompts")
    prompt_file = os.path.join(prompt_dir, prompt)
    if os.path.exists(prompt_file):
        with open(prompt_file, "r") as f:
            return f.read()
    return None

@pynvim.plugin
class LLMPlugin:
    def __init__(self, nvim):
        self.nvim = nvim


    @pynvim.function("LLMResponse")
    def llm_response(self, args):
        history = self._get_chat_history()
        prompt = get_system_prompt()
        if prompt:
            history = [{"role": "system", "content": prompt}] + history

        model = self.nvim.vars.get("llm_model", "claude-3-5-sonnet-20240620")

        if len(history) > 0:
            self.make_llm_request(history, model)

    def make_llm_request(self, history, model):
        response = litellm.completion(
            model=model,
            messages=history,
            max_tokens=4000,
            stream=True
        )

        initial_paste_value = self.nvim.command_output('set paste?')
        self.nvim.command('set paste')
        self.nvim.feedkeys("oLLM: ")

        total_response = ""
        interrupted = False
        try:
            for chunk in response:
                current_line = self.nvim.call('getline', '.')
                prefix = ""
                if current_line.startswith("LLM: "):
                    prefix = "LLM: "
                    current_line = current_line[5:]
                if len(current_line) != 0 and current_line != total_response[-len(current_line):]:
                    last_line_response = total_response.split("\n")[-1]
                    diff = line_diff(last_line_response, current_line)
                    self.nvim.feedkeys("\x03cc{}{}\n> {}\x03".format(prefix, last_line_response, diff))

                    interrupted = True
                    break
                delta = chunk.choices[0].delta.content
                if delta:
                    self.nvim.feedkeys(delta)
                    total_response += delta
        except KeyboardInterrupt:
            self.nvim.command('echom "Keyboard Interrupt received"')
        finally:
            if not interrupted:
                self.nvim.feedkeys("\x03o> \x03")
            self.nvim.command('set {}'.format(initial_paste_value))
            if interrupted:
                self.nvim.feedkeys("a")

    def _get_chat_history(self):
        cursor_line, _ = self.nvim.current.window.cursor
        lines = self.nvim.current.buffer[:cursor_line]
        for i, line in enumerate(lines[::-1]):
            if line.startswith(">>"):
                lines = lines[len(lines) - i - 1:]
                break

        history = []

        for line in lines:
            if line.startswith("//") or line.startswith("#"):
                continue
            if line.startswith("LLM:"):
                history.append({"role": "assistant", "content": line[4:].strip()})
            elif line.startswith(">"):
                line = line.lstrip('>').strip()
                history.append({"role": "user", "content": line})
            else:
                if len(history) > 0:
                    history[-1]["content"] += "\n" + line.strip()
        return history
