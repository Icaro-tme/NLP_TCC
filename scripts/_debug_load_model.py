import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

repo='facebook/m2m100_418M'
print('torch', torch.__version__, 'cuda', torch.cuda.is_available())
print('loading tokenizer...')
_ = AutoTokenizer.from_pretrained(repo)
print('loading model...')
model = AutoModelForSeq2SeqLM.from_pretrained(repo, use_safetensors=True, low_cpu_mem_usage=True)
print('loaded; any meta?', any(p.is_meta for p in model.parameters()))
if any(p.is_meta for p in model.parameters()):
	# materializa parametros vazios antes de mover
	for name, param in model.named_parameters():
		if param.is_meta:
			with torch.no_grad():
				param.data = torch.empty(param.shape, dtype=param.dtype, device='cuda')
	for name, buf in model.named_buffers():
		if buf.is_meta:
			buf.data = torch.empty(buf.shape, dtype=buf.dtype, device='cuda')
	print('meta params allocated directly on cuda')
else:
	print('no meta params; moving normally')
	model.to('cuda')
print('final device of first param:', next(model.parameters()).device)
