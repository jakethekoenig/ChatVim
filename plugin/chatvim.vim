" Define the normal mode mapping
nnoremap <silent> <leader>g :call chatvim#GPTResponse()<CR>

" Define the insert mode mappings
inoremap ?? ?<Esc>:call chatvim#GPTResponse()<CR>
inoremap .. .<Esc>:call chatvim#GPTResponse()<CR>

