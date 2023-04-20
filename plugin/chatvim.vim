" Define the normal mode mapping
nnoremap <silent> <leader>g :call chatvim#GPTResponse()<CR>

" Define the insert mode mappings
inoremap <S-CR> <C-o>:call chatvim#GPTResponse()<CR><C-o>a
inoremap <C-CR> <C-o>:call chatvim#GPTResponse()<CR><C-o>a

