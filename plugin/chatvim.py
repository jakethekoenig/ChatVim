import os
import litellm
import pynvim
import threading
import time

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
        self.completion_active = False
        self.completion_thread = None


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
        if self.completion_active:
            return
        
        # Store the target buffer and position
        target_buffer = self.nvim.current.buffer
        cursor_line, _ = self.nvim.current.window.cursor
        target_line = cursor_line  # 0-indexed
        
        # Add the initial "LLM: " line (append inserts after target_line)
        target_buffer.append(["LLM: "], target_line)
        
        # Move cursor to the new line
        self.nvim.current.window.cursor = (target_line + 1, 5)
        
        self.completion_active = True
        
        # Start the completion in a separate thread
        self.completion_thread = threading.Thread(
            target=self._stream_completion,
            args=(history, model, target_buffer, target_line + 1)
        )
        self.completion_thread.daemon = True
        self.completion_thread.start()

    def _stream_completion(self, history, model, target_buffer, target_line):
        try:
            response = litellm.completion(
                model=model,
                messages=history,
                max_tokens=4000,
                stream=True
            )

            total_response = ""
            completed_normally = True
            
            for chunk in response:
                if not self.completion_active:
                    completed_normally = False
                    break
                    
                delta = chunk.choices[0].delta.content
                if delta:
                    total_response += delta
                    
                    # Update the buffer using async_call to ensure thread safety
                    self.nvim.async_call(self._update_buffer, target_buffer, target_line, total_response)
                    
        except Exception as e:
            self.nvim.async_call(self.nvim.command, f'echom "LLM completion error: {str(e).replace('"', '\\"')}"')
            completed_normally = False
        finally:
            self.completion_active = False
            # Add a new user prompt line only if completion finished normally
            if completed_normally:
                self.nvim.async_call(self._finish_completion, target_buffer, target_line, total_response)

    def _update_buffer(self, target_buffer, start_line, total_response):
        if not self.completion_active:
            return
            
        try:
            # Check if user has modified the buffer (interruption detection)
            if self._check_for_user_interruption(target_buffer, start_line, total_response):
                self.completion_active = False
                return
                
            # Split the total response into lines and prepend "LLM: " to the first line
            response_lines = total_response.split('\n')
            lines_to_write = ["LLM: " + response_lines[0]]
            if len(response_lines) > 1:
                lines_to_write.extend(response_lines[1:])
                
            # Update the buffer with new content
            for i, line in enumerate(lines_to_write):
                line_num = start_line + i
                if line_num < len(target_buffer):
                    target_buffer[line_num] = line
                else:
                    target_buffer.append(line)
                    
        except Exception as e:
            self.nvim.command(f'echom "Buffer update error: {str(e).replace('"', '\\"')}"')
            self.completion_active = False

    def _check_for_user_interruption(self, target_buffer, start_line, expected_response):
        """Check if user has modified the buffer, indicating interruption"""
        try:
            # Build expected lines from the response
            response_lines = expected_response.split('\n')
            expected_lines = ["LLM: " + response_lines[0]]
            if len(response_lines) > 1:
                expected_lines.extend(response_lines[1:])
            
            # Check if any of the expected lines have been modified
            for i, expected_line in enumerate(expected_lines):
                line_num = start_line + i
                if line_num < len(target_buffer):
                    current_line = target_buffer[line_num]
                    # If the current line doesn't match what we expect, user interrupted
                    if current_line != expected_line:
                        return True
                else:
                    # If we're expecting more lines than exist, something's wrong
                    return True
                    
            return False
        except:
            return True

    def _finish_completion(self, target_buffer, start_line, total_response):
        """Add the user prompt line after completion"""
        try:
            # Find the last line of the response
            response_lines = total_response.split('\n')
            last_line_num = start_line + len(response_lines) - 1
            
            # Add a new user prompt line
            target_buffer.append("> ", last_line_num)
            
        except Exception as e:
            self.nvim.command(f'echom "Completion finish error: {str(e)}"')

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
