#!/usr/bin/env bash
# Publica a API do ArchIQ no AWS Lambda com uma Function URL (HTTPS, sem API Gateway, sem load balancer).
# Pode rodar de novo a qualquer momento: cria o que falta e atualiza o resto.
#
# Precisa de um perfil da AWS CLI com permissao de IAM e Lambda (o usuario arch-iq-app NAO tem):
#   AWS_PROFILE=admin bash deploy/lambda/deploy.sh
# Le os nomes dos recursos do .env (tabela, bucket, topico, Cognito); as chaves do .env nao sao usadas:
# no Lambda as permissoes vem da role criada aqui.
set -euo pipefail
cd "$(dirname "$0")/../.."

FN="${FN:-arch-iq-api}"
ROLE="${FN}-role"
REGION="${REGION:-us-east-1}"
SITE_ORIGIN="${SITE_ORIGIN:-https://limajoaohs.github.io}"
# Camada oficial do Lambda Web Adapter (awslabs/aws-lambda-web-adapter), x86_64
ADAPTER_LAYER="arn:aws:lambda:${REGION}:753240598075:layer:LambdaAdapterLayerX86:30"
AWS="aws --region $REGION"

envval() { grep -E "^$1=" .env | head -1 | cut -d= -f2- | tr -d '"\r'; }
MODEL_ID="$(envval BEDROCK_MODEL_ID)"; MODEL_ID="${MODEL_ID:-amazon.nova-lite-v1:0}"
KB_ID="$(envval BEDROCK_KB_ID)"
BUCKET="$(envval S3_REPORTS_BUCKET)"
TABLE="$(envval DYNAMODB_TABLE_NAME)"
TOPIC="$(envval SNS_TOPIC_ARN)"
POOL="$(envval COGNITO_USER_POOL_ID)"
CLIENT="$(envval COGNITO_CLIENT_ID)"
ACCOUNT="$($AWS sts get-caller-identity --query Account --output text)"
echo "Conta $ACCOUNT, regiao $REGION, funcao $FN"

# 1. Role com o minimo que o codigo usa (src/aws/*)
STATEMENTS="{\"Effect\":\"Allow\",\"Action\":\"bedrock:InvokeModel\",\"Resource\":\"arn:aws:bedrock:${REGION}::foundation-model/${MODEL_ID}\"}"
[ -n "$KB_ID" ]  && STATEMENTS+=",{\"Effect\":\"Allow\",\"Action\":\"bedrock:Retrieve\",\"Resource\":\"arn:aws:bedrock:${REGION}:${ACCOUNT}:knowledge-base/${KB_ID}\"}"
[ -n "$BUCKET" ] && STATEMENTS+=",{\"Effect\":\"Allow\",\"Action\":\"s3:PutObject\",\"Resource\":\"arn:aws:s3:::${BUCKET}/*\"}"
[ -n "$TABLE" ]  && STATEMENTS+=",{\"Effect\":\"Allow\",\"Action\":[\"dynamodb:GetItem\",\"dynamodb:PutItem\",\"dynamodb:Query\",\"dynamodb:DeleteItem\"],\"Resource\":\"arn:aws:dynamodb:${REGION}:${ACCOUNT}:table/${TABLE}\"}"
[ -n "$TOPIC" ]  && STATEMENTS+=",{\"Effect\":\"Allow\",\"Action\":\"sns:Publish\",\"Resource\":\"${TOPIC}\"}"
STATEMENTS+=",{\"Effect\":\"Allow\",\"Action\":[\"cloudwatch:PutMetricData\",\"textract:DetectDocumentText\"],\"Resource\":\"*\"}"
POLICY="{\"Version\":\"2012-10-17\",\"Statement\":[${STATEMENTS}]}"
TRUST='{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}'

if ! $AWS iam get-role --role-name "$ROLE" >/dev/null 2>&1; then
  $AWS iam create-role --role-name "$ROLE" --assume-role-policy-document "$TRUST" >/dev/null
  $AWS iam attach-role-policy --role-name "$ROLE" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
  echo "Role criada; aguardando a propagacao do IAM"; sleep 10
fi
$AWS iam put-role-policy --role-name "$ROLE" --policy-name archiq-app --policy-document "$POLICY"
ROLE_ARN="arn:aws:iam::${ACCOUNT}:role/${ROLE}"

# 2. Pacote
python deploy/lambda/build_zip.py
ZIP=dist/archiq-lambda.zip

# 3. Funcao. AWS_REGION e reservada pelo Lambda e ja vem preenchida.
ENV_JSON="{\"Variables\":{\"AWS_LAMBDA_EXEC_WRAPPER\":\"/opt/bootstrap\",\"PORT\":\"8080\",\"AWS_LWA_READINESS_CHECK_PATH\":\"/health\",\
\"CORS_ORIGINS\":\"${SITE_ORIGIN}\",\"BEDROCK_MODEL_ID\":\"${MODEL_ID}\",\"BEDROCK_KB_ID\":\"${KB_ID}\",\"S3_REPORTS_BUCKET\":\"${BUCKET}\",\
\"DYNAMODB_TABLE_NAME\":\"${TABLE}\",\"SNS_TOPIC_ARN\":\"${TOPIC}\",\"COGNITO_USER_POOL_ID\":\"${POOL}\",\"COGNITO_CLIENT_ID\":\"${CLIENT}\"}}"
COMMON=(--handler run.sh --timeout 60 --memory-size 1024 --layers "$ADAPTER_LAYER" --environment "$ENV_JSON")

if $AWS lambda get-function --function-name "$FN" >/dev/null 2>&1; then
  $AWS lambda update-function-code --function-name "$FN" --zip-file "fileb://$ZIP" >/dev/null
  $AWS lambda wait function-updated --function-name "$FN"
  $AWS lambda update-function-configuration --function-name "$FN" --runtime python3.11 --role "$ROLE_ARN" "${COMMON[@]}" >/dev/null
else
  $AWS lambda create-function --function-name "$FN" --runtime python3.11 --architectures x86_64 \
    --role "$ROLE_ARN" --zip-file "fileb://$ZIP" "${COMMON[@]}" >/dev/null
fi
$AWS lambda wait function-updated --function-name "$FN"

# Logs por 14 dias, para o CloudWatch Logs nao acumular custo
$AWS logs create-log-group --log-group-name "/aws/lambda/$FN" 2>/dev/null || true
$AWS logs put-retention-policy --log-group-name "/aws/lambda/$FN" --retention-in-days 14

# 4. Endereco HTTPS publico. O CORS fica so na API (CORSMiddleware), para nao duplicar cabecalhos.
if ! $AWS lambda get-function-url-config --function-name "$FN" >/dev/null 2>&1; then
  $AWS lambda create-function-url-config --function-name "$FN" --auth-type NONE >/dev/null
  $AWS lambda add-permission --function-name "$FN" --statement-id public-url \
    --action lambda:InvokeFunctionUrl --principal '*' --function-url-auth-type NONE >/dev/null
fi
URL="$($AWS lambda get-function-url-config --function-name "$FN" --query FunctionUrl --output text)"
echo
echo "API no ar: $URL"
echo "Teste:     curl ${URL}health"
echo "Depois:    troque baseUrl em web/config.js para ${URL%/}"
