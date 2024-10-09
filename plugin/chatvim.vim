let s:path = expand('<sfile>:p:h')
call remote#host#RegisterPlugin('python3', s:path.'/chatvim.py', [
      \ {'sync': v:false, 'name': 'LLMResponse', 'type': 'function', 'opts': {}},
     \ ])
" Define the normal mode mapping
nnoremap <silent> <leader>g :call LLMResponse()<CR>
