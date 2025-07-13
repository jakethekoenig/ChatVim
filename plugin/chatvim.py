import os
import litellm
import pynvim
import threading

# Constants
LLM_PREFIX = "LLM: "
USER_PREFIX = "> "

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
        self.completion_active = threading.Event()
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
        if self.completion_active.is_set():
            self.nvim.command('echom "LLM completion already in progress"')
            return
        
        # Store the target buffer handle and position for thread safety
        target_buffer = self.nvim.current.buffer
        buffer_handle = target_buffer.handle
        cursor_line, _ = self.nvim.current.window.cursor  # 1-based line number
        target_line = cursor_line - 1  # Convert to 0-based for buffer operations
        
        # Add the initial "LLM: " line (append inserts after target_line)
        target_buffer.append([LLM_PREFIX], target_line)
        
        # Move cursor to the new line (1-based coordinates)
        self.nvim.current.window.cursor = (cursor_line + 1, len(LLM_PREFIX))
        
        self.completion_active.set()
        
        # Start the completion in a separate thread
        self.completion_thread = threading.Thread(
            target=self._stream_completion,
            args=(history, model, buffer_handle, target_line + 1)
        )
        self.completion_thread.daemon = True
        self.completion_thread.start()

    def _stream_completion(self, history, model, buffer_handle, target_line):
        thread = threading.current_thread()
        try:
            response = litellm.completion(
                model=model,
                messages=history,
                max_tokens=4000,
                stream=True
            )

            total_response = ""
            completed_normally = True
            last_update_len = 0
            
            for chunk in response:
                if not self.completion_active.is_set():
                    completed_normally = False
                    break
                    
                delta = chunk.choices[0].delta.content
                if delta:
                    total_response += delta
                    
                    # Throttle updates to avoid flooding the UI - only update every 20 characters
                    if len(total_response) - last_update_len >= 20 or '\n' in delta:
                        last_update_len = len(total_response)
                        self.nvim.async_call(self._update_buffer, buffer_handle, target_line, total_response)
                    
                    # Check if completion was interrupted after scheduling update
                    if not self.completion_active.is_set():
                        completed_normally = False
                        break
            
            # Final update to ensure all content is written
            if completed_normally and len(total_response) > last_update_len:
                self.nvim.async_call(self._update_buffer, buffer_handle, target_line, total_response)
                    
        except Exception as e:
            error_msg = str(e).replace('"', r'\"')
            self.nvim.async_call(self.nvim.command, f'echom "LLM completion error: {error_msg}"')
            completed_normally = False
        finally:
            # Check one more time in case interruption happened right before finally
            if not self.completion_active.is_set():
                completed_normally = False
            self.completion_active.clear()
            
            # Join the thread with timeout to avoid leaks
            if self.completion_thread and self.completion_thread != thread:
                self.completion_thread.join(timeout=0.1)
            self.completion_thread = None
            
            # Add a new user prompt line only if completion finished normally
            if completed_normally:
                self.nvim.async_call(self._finish_completion, buffer_handle, target_line, total_response)

    def _update_buffer(self, buffer_handle, start_line, total_response):
        if not self.completion_active.is_set():
            return
            
        try:
            # Get the buffer from the buffer handle
            target_buffer = self.nvim.api.nvim_get_buf_by_handle(buffer_handle)
            
            # Check if user has modified the buffer or entered insert mode (interruption detection)
            if self._check_for_user_interruption(target_buffer, start_line, total_response, buffer_handle):
                self.completion_active.clear()
                return
                
            # Split the total response into lines and prepend "LLM: " to the first line
            response_lines = total_response.split('\n')
            # Only add LLM_PREFIX if the first line doesn't already have it
            first_line = response_lines[0]
            if not first_line.startswith(LLM_PREFIX):
                first_line = LLM_PREFIX + first_line
            lines_to_write = [first_line]
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
            error_msg = str(e).replace('"', r'\"')
            self.nvim.command(f'echom "Buffer update error: {error_msg}"')
            self.completion_active.clear()

    def _check_for_user_interruption(self, target_buffer, start_line, expected_response, buffer_handle):
        """Check if user has modified the buffer or entered insert mode, indicating interruption"""
        try:
            # Check if user is in insert mode and in the target buffer
            current_buffer = self.nvim.current.buffer
            if current_buffer.handle == buffer_handle:
                current_mode = self.nvim.call('mode')
                if current_mode.startswith('i') or current_mode.startswith('R'):
                    return True
            
            # Build expected lines from the response
            response_lines = expected_response.split('\n')
            first_line = response_lines[0]
            if not first_line.startswith(LLM_PREFIX):
                first_line = LLM_PREFIX + first_line
            expected_lines = [first_line]
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

    def _finish_completion(self, buffer_handle, start_line, total_response):
        """Add the user prompt line after completion"""
        try:
            # Get the buffer from the buffer handle
            target_buffer = self.nvim.api.nvim_get_buf_by_handle(buffer_handle)
            
            # Find the last line of the response
            response_lines = total_response.split('\n')
            last_line_num = start_line + len(response_lines) - 1
            
            # Add a new user prompt line
            target_buffer.append([USER_PREFIX], last_line_num)
            
            # Move cursor to the new user prompt line for easy typing
            # Check if this buffer is currently active
            if self.nvim.current.buffer.handle == buffer_handle:
                self.nvim.current.window.cursor = (last_line_num + 2, len(USER_PREFIX))
            
        except Exception as e:
            error_msg = str(e).replace('"', r'\"')
            self.nvim.command(f'echom "Completion finish error: {error_msg}"')

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
            if line.startswith(LLM_PREFIX) or line.startswith("LLM:"):
                # Support both old format "LLM:" and new format "LLM: " for back-compatibility
                if line.startswith(LLM_PREFIX):
                    content = line[len(LLM_PREFIX):].strip()
                else:
                    content = line[4:].strip()
                history.append({"role": "assistant", "content": content})
            elif line.startswith(">"):
                line = line.lstrip('>').strip()
                history.append({"role": "user", "content": line})
            else:
                if len(history) > 0:
                    history[-1]["content"] += "\n" + line.strip()
        return history
