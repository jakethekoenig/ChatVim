# Chat Vim

This is a plugin to talk to Chat GPT in neovim. To talk to ChatGPT in normal mode type `<leader>g` or in insert mode type `??` or '..'. The plugin will take lines starting with `GPT:` or following those lines as from GPT and lines starting with `>` as from you. If you want to start a new chat in the same file start a line with `>>`.

![](chat.gif)

# Installation

```bash
git clone https://github.com/jakethekoenig/ChatVim.git ~/.vim/pack/misc/start/
cd ~/.vim/pack/misc/start/
pip install -r requirements.txt # Only openai and pynvim
export OPENAI_API_KEY=<YOUR API KEY> # If not already set
```

# Usage

The plugin infers a chat structure from lines starting with `GPT:` `>` and `>>`. It gives this chat to GPT and inserts the response upon `<leader>g` in normal mode or `??` in insert mode. 

You can control which model you're talking to by writing `3>` or `4>` or by setting the global variable `gpt_model` to the full name of the model you want to talk to. Writing `3>` trumps the global variable.
