# Chat Vim

This is a plugin to talk to LLMs in neovim. To talk to an LLM in normal mode type `<leader>g`. The plugin will take lines starting with `LLM:` or following those lines as from LLM and lines starting with `>` as from you. If you want to start a new chat in the same file start a line with `>>`.

![](chat2.gif)

# Installation

```bash
git clone https://github.com/jakethekoenig/ChatVim.git ~/.vim/pack/misc/start/
cd ~/.vim/pack/misc/start/ChatVim
pip install -r requirements.txt # Only litellm and pynvim
# Defaults to sonnet-3.5. Only need to set the API key for the model you want to use.
export ANTHROPIC_API_KEY=<YOUR API KEY>
export OPENAI_API_KEY=<YOUR API KEY>
```

I recommend installing the requirements in a virtual environment. See [here](https://neovim.io/doc/user/provider.html) for how to have a neovim specific virtual environment.

# Usage

The plugin infers a chat structure from the beginning of the file to the current line. The plugin infers who is talking from the following sequences at the start of the line.

| Sequence | Effect |
| --------- | --------- |
| `>>` | Starts a new chat. Previous lines ignored. Speaker is user. |
| `>` | Speaker is user. |
| `LLM:` | Speaker is llm_model. |

You can get a completion from the model with `<leader>g` or `:call LLMResponse()`. The LLM's output is streamed in the next line. You can interrupt the model at any time. Just start typing.

The model defaults to `claude-3-5-sonnet-20240620` but this can be configured by setting `llm_model` in your vimrc. The Plugin uses litellm. See [their documentation](https://docs.litellm.ai/docs/providers) for supported models.
