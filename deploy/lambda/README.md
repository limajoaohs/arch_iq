# API do ArchIQ no AWS Lambda

Tira a API do plano gratuito do Render (512 MB, um processo, dorme sem uso) e a coloca no
AWS Lambda com uma Function URL: um endereço HTTPS, sem API Gateway, load balancer ou IP público.
O código é o mesmo. A camada Lambda Web Adapter repassa cada requisição para o uvicorn.

## Por que Lambda e não App Runner ou ECS

| Opção | Custo mensal estimado | Observação |
|---|---|---|
| **AWS Lambda + Function URL** | **cerca de US$ 0** | Cabe no nível gratuito (abaixo) |
| Amazon ECS Express Mode (Fargate) | cerca de US$ 45 a 65 | Load balancer (US$ 0,0225/h) e IPs públicos (US$ 0,005/h cada) cobram mesmo parados |
| AWS App Runner | — | Não aceita clientes novos desde 30/04/2026 (aviso no site da AWS) |
| Render gratuito (hoje) | US$ 0 | Dorme sem uso; o /health levou 12,7 s para acordar em 11/11/2026 |

Preços de us-east-1 consultados em 11/11/2026 nas páginas de preço da AWS.

## Estimativa de custo no Lambda

- **Nível gratuito do Lambda:** 1 milhão de requisições e 400.000 GB-segundos por mês.
  A página de preços não diz se é permanente ou só no primeiro ano: confira no painel de Billing.
- **Uma análise:** cerca de 5 s com 1 GB de memória = 5 GB-s. O nível gratuito cobre umas 80 mil
  análises por mês. Uma análise que sai do cache leva décimos de segundo.
- **Pico de 1000 análises simultâneas:** cerca de 5.000 GB-s, perto de 1% do nível gratuito.
- **Depois do nível gratuito:** US$ 0,0000166667 por GB-s e US$ 0,20 por milhão de requisições,
  ou seja, cerca de US$ 0,08 a cada 1000 análises.
- **Function URL:** sem cobrança própria na página de preços. Sem ECR: o pacote é um .zip.
- **CloudWatch Logs:** centavos; o deploy guarda os logs por 14 dias.
- **Bedrock:** igual a hoje, por chamada, e menor com o cache de análises.

Com os créditos atuais (cerca de US$ 120), o Lambda praticamente não os consome. O gasto que
continua é o do Bedrock, como já acontece no Render.

## Antes de publicar

1. **Limite de concorrência da conta.** O padrão é 1000 execuções simultâneas por região, mas
   contas novas começam com menos. Veja em Service Quotas → AWS Lambda → "Concurrent executions".
   O pedido de aumento é gratuito.
2. **Um perfil da AWS CLI com permissão de IAM e Lambda.** O usuário `arch-iq-app` do `.env`
   tem permissão mínima e não consegue criar a função nem a role.

## Publicar

```bash
AWS_PROFILE=<seu perfil admin> bash deploy/lambda/deploy.sh
```

O script cria a role `arch-iq-api-role` com o mínimo que o código usa (Bedrock, a tabela
DynamoDB, o bucket S3, o tópico SNS, métricas e Textract), monta o pacote, cria ou atualiza a
função e imprime a URL. Rodar de novo só atualiza.

Depois:

1. `curl <URL>health` deve responder `{"status":"healthy",...}`.
2. Troque `baseUrl` em `web/config.js` pela URL (sem a barra final) e publique o site.
3. Teste login, uma análise e uma pergunta no site.
4. Com tudo certo por alguns dias, desligue o serviço no Render.

Para voltar atrás, basta devolver o `baseUrl` antigo em `web/config.js`: o Render continua de pé.

## O que muda no comportamento

- Cada instância do Lambda atende uma requisição por vez e o Lambda abre outras no pico.
  O limite de 4 chamadas ao Bedrock passa a valer por instância, então num pico o Bedrock
  pode recusar por excesso. Nesse caso o boto3 tenta de novo e, sem sucesso, a análise sai com
  o texto de reserva. Para segurar o pico de vez, o próximo passo é uma fila no Amazon SQS.
- O cache em memória vale por instância; o cache no DynamoDB é compartilhado por todas.
- A primeira requisição depois de um tempo parado leva cerca de 1 a 2 s a mais (cold start).
