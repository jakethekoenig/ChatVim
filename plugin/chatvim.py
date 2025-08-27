import os
import litellm
import pynvim
import threading

# Constants
LLM_PREFIX = "LLM: "
USER_PREFIX = "> "
THROTTLE_CHARS = 20

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
        
        try:
            # Store the target buffer handle and position for thread safety
            target_buffer = self.nvim.current.buffer
            buffer_handle = target_buffer.handle
            cursor_line, _ = self.nvim.current.window.cursor  # 1-based line number
            target_line = cursor_line - 1  # Convert to 0-based for buffer operations
            
            # Add the initial "LLM: " line (append inserts after target_line)
            target_buffer.append([LLM_PREFIX.rstrip()], target_line)
            
            # Move cursor to the new line (1-based coordinates)
            self.nvim.current.window.cursor = (cursor_line + 1, len(LLM_PREFIX))
            
            self.completion_active.set()
            
            # Add some debug info
            self.nvim.command(f'echom "Starting LLM completion with model: {model}"')
            
            # Start the completion in a separate thread
            self.completion_thread = threading.Thread(
                target=self._stream_completion,
                args=(history, model, buffer_handle, target_line + 1)
            )
            self.completion_thread.daemon = True
            self.completion_thread.start()
            
        except Exception as e:
            error_msg = str(e).replace('"', r'\"')
            self.nvim.command(f'echom "Error starting LLM request: {error_msg}"')
            self.completion_active.clear()

    def _stream_completion(self, history, model, buffer_handle, target_line):
        """Stream LLM completion to the buffer in a background thread"""
        response = None
        try:
            # Debug: Log that we're starting the completion
            self.nvim.async_call(self.nvim.command, 'echom "Thread started, calling litellm..."')
            
            response = litellm.completion(
                model=model,
                messages=history,
                max_tokens=4000,
                stream=True
            )

            # Debug: Log that we got a response
            self.nvim.async_call(self.nvim.command, 'echom "Got response from litellm, starting stream..."')

            total_response = ""
            completed_normally = True
            last_update_len = 0
            chunk_count = 0
            
            for chunk in response:
                chunk_count += 1
                if not self.completion_active.is_set():
                    completed_normally = False
                    break
                    
                delta = chunk.choices[0].delta.content
                if delta:
                    total_response += delta
                    
                    # Update more frequently initially to show progress
                    should_update = (
                        len(total_response) - last_update_len >= THROTTLE_CHARS or 
                        '\n' in delta or 
                        chunk_count <= 3  # Always update first few chunks
                    )
                    
                    if should_update:
                        last_update_len = len(total_response)
                        self.nvim.async_call(self._update_buffer, buffer_handle, target_line, total_response)
                    
                    # Check if completion was interrupted after scheduling update
                    if not self.completion_active.is_set():
                        completed_normally = False
                        break
            
            # Final update to ensure all content is written
            if completed_normally and len(total_response) > last_update_len:
                self.nvim.async_call(self._update_buffer, buffer_handle, target_line, total_response)
            
            # Debug: Log completion status
            self.nvim.async_call(self.nvim.command, f'echom "Stream completed. Chunks: {chunk_count}, Response length: {len(total_response)}"')
                    
        except Exception as e:
            error_msg = str(e).replace('"', r'\"')
            self.nvim.async_call(self.nvim.command, f'echom "LLM completion error: {error_msg}"')
            completed_normally = False
        finally:
            # Close the response stream to free resources
            if response:
                try:
                    getattr(response, "close", lambda: None)()
                except:
                    pass
            
            # Check one more time in case interruption happened right before finally
            if not self.completion_active.is_set():
                completed_normally = False
            self.completion_active.clear()
            self.completion_thread = None
            
            # Add a new user prompt line only if completion finished normally
            if completed_normally:
                self.nvim.async_call(self._finish_completion, buffer_handle, target_line, total_response)
            else:
                # If completion failed, at least add the user prompt
                self.nvim.async_call(self._add_user_prompt_after_failure, buffer_handle, target_line)

    def _update_buffer(self, buffer_handle, start_line, total_response):
        """Update the buffer with new response content"""
        # Don't check completion_active here to allow final updates to complete
            
        try:
            # Check if buffer is still loaded
            if not self.nvim.api.buf_is_loaded(buffer_handle):
                self.completion_active.clear()
                return
                
            # Get the buffer from the buffer handle
            target_buffer = self.nvim.from_handle(buffer_handle)
            
            # Split the total response into lines
            response_lines = total_response.split('\n')
            
            # Build the lines to write - first line gets "LLM: " prefix
            lines_to_write = [LLM_PREFIX + response_lines[0]]
            if len(response_lines) > 1:
                lines_to_write.extend(response_lines[1:])
                
            # Update the buffer with new content
            for i, line in enumerate(lines_to_write):
                line_num = start_line + i
                if line_num >= len(target_buffer):
                    target_buffer.append([line])
                else:
                    target_buffer[line_num] = line
            
            # Check if user has modified the buffer or entered insert mode (interruption detection)
            # Do this AFTER updating to avoid false positives on first update
            if self.completion_active.is_set() and self._check_for_user_interruption(target_buffer, start_line, total_response, buffer_handle):
                self.completion_active.clear()
                return
                    
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
                current_mode = self.nvim.call('mode', 1)  # Non-blocking mode call
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
            # Check if buffer is still loaded
            if not self.nvim.api.buf_is_loaded(buffer_handle):
                return
                
            # Get the buffer from the buffer handle
            target_buffer = self.nvim.from_handle(buffer_handle)
            
            # Find the last line of the response
            response_lines = total_response.split('\n')
            last_line_num = start_line + len(response_lines) - 1
            
            # Add a new user prompt line
            target_buffer.append([USER_PREFIX], last_line_num)
            
            # Only move cursor if user hasn't switched buffers since completion started
            # and if the user wants cursor positioning (check for a setting)
            move_cursor = self.nvim.vars.get('chatvim_move_cursor_after_completion', True)
            if move_cursor and self.nvim.current.buffer.handle == buffer_handle:
                self.nvim.current.window.cursor = (last_line_num + 2, len(USER_PREFIX))
            
        except Exception as e:
            error_msg = str(e).replace('"', r'\"')
            self.nvim.command(f'echom "Completion finish error: {error_msg}"')

    def _add_user_prompt_after_failure(self, buffer_handle, start_line):
        """Add user prompt line after a failed completion"""
        try:
            # Check if buffer is still loaded
            if not self.nvim.api.buf_is_loaded(buffer_handle):
                return
                
            # Get the buffer from the buffer handle
            target_buffer = self.nvim.from_handle(buffer_handle)
            
            # Add a new user prompt line after the LLM line
            target_buffer.append([USER_PREFIX], start_line)
            
        except Exception as e:
            error_msg = str(e).replace('"', r'\"')
            self.nvim.command(f'echom "Error adding user prompt: {error_msg}"')

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
