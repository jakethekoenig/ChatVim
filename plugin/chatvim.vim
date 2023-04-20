" Define the normal mode mapping
nnoremap <silent> <leader>g :call chatvim#GPTResponse()<CR>

" Define the insert mode mappings
inoremap ?? ?<C-o>:call chatvim#GPTResponse()<CR><C-o>a
inoremap .. .<C-o>:call chatvim#GPTResponse()<CR><C-o>a

