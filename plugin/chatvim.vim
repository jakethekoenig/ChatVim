let s:path = expand('<sfile>:p:h')
call remote#host#RegisterPlugin('python3', s:path.'/chatvim.py', [
      \ {'sync': v:false, 'name': 'GPTResponse', 'type': 'function', 'opts': {}},
     \ ])
" Define the normal mode mapping
nnoremap <silent> <leader>g :call GPTResponse()<CR>

" Define the insert mode mappings
inoremap ?? ?<Esc>:call GPTResponse()<CR>
inoremap .. .<Esc>:call GPTResponse()<CR>
