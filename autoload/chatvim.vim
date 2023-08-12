
function! chatvim#test(response)
    echom a:response
    setlocal paste
    execute "normal! oGPT: " . a:response
    execute "normal! o>"
    redraw
    setlocal nopaste
endfunction

function! chatvim#GPTResponse()
  python3 << EOF
import sys
import os

# Add the plugin's pythonx directory to the Python import path
pythonx_path = vim.eval('expand("<sfile>:p:h")') + '/../pythonx'
if pythonx_path not in sys.path:
  sys.path.append(pythonx_path)

from chatvim.gpt_plugin import GPTPlugin
GPTPlugin(vim).gpt_response()
EOF
endfunction
