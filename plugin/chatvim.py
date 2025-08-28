import os
import threading
import litellm
import pynvim


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
        # Track active streaming requests by buffer number
        # { bufnr: {"cancel": False, "start_line": int, "prefix": "LLM: ", "last_len": int} }
        self.active_requests = {}


    @pynvim.function("LLMResponse")
    def llm_response(self, args):
        history = self._get_chat_history()
        prompt = get_system_prompt()
        if prompt:
            history = [{"role": "system", "content": prompt}] + history

        model = self.nvim.vars.get("llm_model", "claude-3-5-sonnet-20240620")

        if len(history) == 0:
            return

        # Prepare target buffer and insertion point
        buf = self.nvim.current.buffer
        bufnr = buf.number
        cursor_line, _ = self.nvim.current.window.cursor
        insert_at = cursor_line  # We will insert after the cursor line
        prefix = "LLM: "

        # Compute insertion index: window.cursor is 1-based; Buffer.append inserts after 0-based index
        insert_at = cursor_line - 1  # insert after cursor line

        # Insert the initial output line synchronously to avoid race conditions
        try:
            buf.append(prefix, insert_at)
        except Exception:
            pass

        # Setup autocmds to interrupt on edits/insert in this buffer
        self._setup_interrupt_autocmds(bufnr)

        # If a previous request exists for this buffer, cancel and clean it up
        prev = self.active_requests.get(bufnr)
        if prev:
            prev["cancel"] = True
            # Let finalize/cleanup handle augroup removal

        # Register active request
        # Keep a direct buffer handle and track last_len (lines written). Start with 1 for the initial "LLM: " line.
        self.active_requests[bufnr] = {
            "cancel": False,
            "start_line": insert_at + 2,  # inserted line is at cursor_line + 1; store 1-based line number
            "prefix": prefix,
            "last_len": 1,
            "buf": buf,
        }

        # Start streaming in background
        threading.Thread(target=self.make_llm_request, args=(history, model, bufnr), daemon=True).start()

    def make_llm_request(self, history, model, bufnr):
        """
        Stream LLM output into a fixed buffer/region without taking insert mode,
        allowing the user to switch buffers. Interrupts if user edits or enters insert in that buffer.
        """
        try:
            response = litellm.completion(
                model=model,
                messages=history,
                max_tokens=4000,
                stream=True
            )
        except Exception as e:
            # Surface error to user
            def _echo_err():
                self.nvim.command(f'echom "ChatVim error: {str(e).replace(\'"\', "\'")}"')
            self.nvim.async_call(_echo_err)
            self._cleanup_request(bufnr)
            return

        total_response = ""
        interrupted = False

        def _write_output():
            # Write the accumulated response into the target buffer region
            req = self.active_requests.get(bufnr)
            if not req:
                return
            try:
                buf = req.get("buf")
                if buf is None:
                    return
                start = req["start_line"]
                prefix = req["prefix"]
                text = prefix + total_response
                # Split into lines (without trailing newline chars)
                lines = text.split("\n")
                # Replace only the previously written region to avoid OOB
                start0 = start - 1  # 0-based
                prev_len = req.get("last_len", 1)
                end0 = start0 + prev_len
                buf.api.set_lines(start0, end0, False, lines)
                req["last_len"] = len(lines)
            except Exception:
                pass

        try:
            for chunk in response:
                # Check for cancellation
                req = self.active_requests.get(bufnr)
                if not req or req.get("cancel"):
                    interrupted = True
                    break
                # Extract delta content depending on provider schema
                delta = None
                ch = chunk
                # Anthropic/OpenAI via litellm: prefer 'choices[0].delta.content' if available, else chunk.choices[0].text, else chunk.delta
                try:
                    delta = ch.choices[0].delta.content
                except Exception:
                    try:
                        delta = ch.choices[0].text
                    except Exception:
                        try:
                            delta = ch.delta
                        except Exception:
                            delta = None
                if delta:
                    total_response += delta
                    self.nvim.async_call(_write_output)
        except KeyboardInterrupt:
            interrupted = True
        finally:
            self._finalize_stream(bufnr, interrupted, total_response)

    def _get_chat_history(self):
        cursor_line, _ = self.nvim.current.window.cursor
        lines = self.nvim.current.buffer[:cursor_line]
        for i, line in enumerate(lines[::-1]):
            # Want to allow copying python interactive sessions
            if line.startswith(">>") and not line.startswith(">>>"):
                lines = lines[len(lines) - i - 1:]
                break

        history = []

        for line in lines:
            if line.startswith("LLM:"):
                history.append({"role": "assistant", "content": line[4:].strip()})
            elif line.startswith(">") and not line.startswith(">>>"):
                line = line.lstrip('>').strip()
                history.append({"role": "user", "content": line})
            else:
                if len(history) > 0:
                    history[-1]["content"] += "\n" + line.strip()
        return history

    @pynvim.function("LLMInterrupt")
    def llm_interrupt(self, args):
        """
        Interrupt an active request for the given buffer number.
        """
        try:
            bufnr = int(args[0]) if args else self.nvim.current.buffer.number
        except Exception:
            bufnr = self.nvim.current.buffer.number
        req = self.active_requests.get(bufnr)
        if req:
            req["cancel"] = True

    def _setup_interrupt_autocmds(self, bufnr: int):
        # Create buffer-local autocmds that notify us when user starts editing
        self.nvim.command(f"augroup ChatVimLLM_{bufnr}")
        self.nvim.command("autocmd!")
        # Define buffer-local autocmds; use <buffer> and pass the actual bufnr via <abuf>
        self.nvim.command("autocmd InsertEnter <buffer> call LLMInterrupt(expand('<abuf>'))")
        self.nvim.command("autocmd TextChanged,TextChangedI <buffer> call LLMInterrupt(expand('<abuf>'))")
        self.nvim.command("augroup END")

    def _cleanup_request(self, bufnr: int):
        # Clear autocmds and active request entry
        try:
            self.nvim.command(f"augroup ChatVimLLM_{bufnr} | autocmd! | augroup END")
        except Exception:
            pass
        if bufnr in self.active_requests:
            del self.active_requests[bufnr]

    def _finalize_stream(self, bufnr: int, interrupted: bool, total_response: str):
        # On completion, optionally add a new user prompt line, then cleanup
        def _finish():
            # Capture the specific request object we intend to finalize
            req = self.active_requests.get(bufnr)
            buf = req.get("buf") if req else None
            if buf is None:
                # Only clean up if this exact req is still current
                if self.active_requests.get(bufnr) is req:
                    self._cleanup_request(bufnr)
                return
            try:
                if not req:
                    return
                if not interrupted:
                    start = req["start_line"]
                    # Determine ending line index (0-based) after writing total_response
                    end0 = (start - 1) + req.get("last_len", 1)
                    # Insert a new prompt line immediately after the streamed block
                    buf.append("> ", end0 - 1)
            finally:
                # Guard: only clean up if we're still the active request
                if self.active_requests.get(bufnr) is req:
                    self._cleanup_request(bufnr)
        self.nvim.async_call(_finish)
