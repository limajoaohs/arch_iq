"""Relatorio para o cliente: a auditoria explicada para quem nao e da area.

E separado da explicacao simplificada (gerada pelo Bedrock): este texto sai de um
catalogo revisado, indexado pelo `code` de cada regra do analisador. Assim ele nao
gasta a cota do Bedrock, nao inventa fatos e funciona mesmo se o LLM estiver fora.

Toda regra nova do analisador precisa de uma entrada aqui; tests/test_client_report.py
falha se faltar alguma.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

PRIORITY_LABEL = {
    1: "Resolver primeiro",
    2: "Resolver em seguida",
    3: "Quando puder",
}

SEVERITY_PRIORITY = {"CRITICAL": 1, "HIGH": 1, "MEDIUM": 2, "LOW": 3}

# Cada risco responde as tres perguntas de quem contrata o servico:
# o que e, o que pode acontecer com o negocio e o que pedir para a equipe tecnica.
RISKS: Dict[str, Dict[str, str]] = {
    "admin_access_open": {
        "title": "A porta de manutenção dos servidores está aberta para a internet",
        "meaning": "O acesso usado para administrar os servidores aceita tentativas de qualquer lugar do mundo, como uma porta dos fundos sem porteiro.",
        "impact": "Robôs tentam senhas nessas portas o tempo todo. Se uma tentativa acertar, alguém de fora pode assumir o servidor e tirar o sistema do ar.",
        "action": "Liberar esse acesso só para os endereços da equipe ou trocar por um acesso gerenciado, sem porta aberta.",
    },
    "port_open": {
        "title": "Há uma entrada do sistema aberta além do necessário",
        "meaning": "Uma parte do sistema aceita conexões de qualquer pessoa na internet, mesmo sem precisar atender o público.",
        "impact": "Cada entrada aberta é mais um ponto que pode ser explorado por quem procura falhas.",
        "action": "Deixar essa entrada acessível apenas para os sistemas e pessoas que realmente precisam dela.",
    },
    "network_rules_missing": {
        "title": "Não encontramos as regras de quem pode acessar o sistema",
        "meaning": "O material analisado não mostra as regras que dizem quem pode entrar. É como não saber se o prédio tem portaria.",
        "impact": "Sem regras claras, fica difícil garantir que só as pessoas e os sistemas certos têm acesso.",
        "action": "Confirmar com a equipe técnica onde essas regras estão definidas e incluí-las na próxima análise.",
    },
    "outbound_open": {
        "title": "O sistema pode enviar dados para qualquer destino",
        "meaning": "Não há limite para onde os servidores podem se conectar. Isso é comum, mas pode ser mais restrito.",
        "impact": "Se um servidor for invadido, fica mais fácil levar dados para fora sem ninguém notar.",
        "action": "Avaliar se vale limitar as saídas aos destinos que o sistema realmente usa.",
    },
    "files_public": {
        "title": "Arquivos guardados na nuvem podem ser vistos por qualquer pessoa",
        "meaning": "A pasta de arquivos está configurada como pública. Quem tiver o endereço consegue abrir o conteúdo, sem senha.",
        "impact": "Se houver documentos ou dados de clientes ali, eles podem vazar. Isso pode gerar problemas com a LGPD e com a confiança dos clientes.",
        "action": "Tornar a pasta privada e liberar o acesso somente para o sistema que precisa dos arquivos.",
    },
    "files_public_guard_missing": {
        "title": "Falta a trava que impede arquivos de ficarem públicos por engano",
        "meaning": "Existe uma proteção geral que bloqueia a publicação acidental de arquivos, e ela não está ligada.",
        "impact": "Um simples erro de configuração no futuro pode deixar arquivos abertos na internet.",
        "action": "Ligar o bloqueio de acesso público em todas as pastas de arquivos.",
    },
    "files_unencrypted": {
        "title": "Os arquivos guardados não estão protegidos por criptografia",
        "meaning": "Criptografia embaralha os dados para que só o sistema autorizado consiga ler. Aqui, ela não aparece configurada.",
        "impact": "Se alguém conseguir uma cópia desses arquivos, poderá ler o conteúdo sem esforço.",
        "action": "Ligar a criptografia das pastas de arquivos. É uma mudança simples e costuma não ter custo relevante.",
    },
    "database_unencrypted": {
        "title": "O banco de dados não está protegido por criptografia",
        "meaning": "As informações do sistema estão guardadas sem a proteção que as torna ilegíveis para quem não tem autorização.",
        "impact": "Em caso de vazamento de uma cópia do banco, os dados ficariam legíveis, incluindo dados de clientes, se existirem ali.",
        "action": "Ativar a criptografia do banco. Pode exigir uma janela curta de manutenção, combinada com antecedência.",
    },
    "database_public": {
        "title": "O banco de dados pode ser alcançado pela internet",
        "meaning": "O lugar onde ficam as informações mais importantes do sistema está exposto, quando deveria ficar em uma área interna.",
        "impact": "Qualquer pessoa pode tentar se conectar a ele. Um erro de senha ou uma falha pode expor todos os dados.",
        "action": "Mover o acesso do banco para a rede interna, deixando-o disponível apenas para o próprio sistema.",
    },
    "database_no_backup": {
        "title": "O banco de dados não tem cópias de segurança garantidas",
        "meaning": "Não encontramos uma rotina que guarde cópias dos dados por tempo suficiente.",
        "impact": "Depois de um erro, de uma falha ou de um ataque, pode não ser possível recuperar as informações perdidas.",
        "action": "Manter cópias automáticas por pelo menos 7 dias e testar a restauração de vez em quando.",
    },
    "database_single_location": {
        "title": "O banco de dados depende de um único local",
        "meaning": "Os dados estão em um só centro de dados, sem uma cópia pronta para assumir em outro local.",
        "impact": "Se esse local tiver problemas, o sistema pode ficar fora do ar até a situação ser resolvida.",
        "action": "Ativar uma segunda cópia em outro local. Isso aumenta o custo, então vale decidir pelo tamanho do prejuízo de ficar parado.",
    },
    "traffic_single_location": {
        "title": "A entrada do sistema depende de um único local",
        "meaning": "O componente que recebe os visitantes está em um só centro de dados.",
        "impact": "Uma falha nesse local pode deixar o sistema fora do ar para todos os usuários.",
        "action": "Distribuir esse componente em pelo menos dois locais.",
    },
    "no_activity_log": {
        "title": "Não há registro de quem fez o quê no ambiente",
        "meaning": "Falta o histórico das ações feitas na conta da nuvem, parecido com as câmeras e o livro de visitas de um prédio.",
        "impact": "Se algo der errado, será difícil descobrir o que aconteceu, quando aconteceu e quem foi o responsável.",
        "action": "Ligar o registro de atividades da conta e guardar esse histórico em local seguro.",
    },
    "no_config_tracking": {
        "title": "Mudanças no ambiente não estão sendo acompanhadas",
        "meaning": "Nenhuma ferramenta está registrando as alterações de configuração feitas ao longo do tempo.",
        "impact": "Uma mudança errada pode passar despercebida e abrir uma falha sem que ninguém saiba.",
        "action": "Ativar o acompanhamento automático das configurações.",
    },
    "no_monitoring": {
        "title": "Ninguém é avisado automaticamente quando algo falha",
        "meaning": "O sistema não tem monitoramento nem alarmes configurados.",
        "impact": "Os problemas podem ser descobertos pelos seus clientes antes da sua equipe.",
        "action": "Configurar registros e alarmes para os serviços principais, com avisos para os responsáveis.",
    },
    "partial_monitoring": {
        "title": "O monitoramento do sistema está incompleto",
        "meaning": "Parte do acompanhamento existe, mas falta a outra metade: os registros ou os alarmes.",
        "impact": "Alguns problemas podem demorar a ser percebidos ou ser difíceis de investigar.",
        "action": "Completar a configuração, mantendo registros e alarmes para os serviços principais.",
    },
    "permissions_too_wide": {
        "title": "Há acessos com mais permissões do que o necessário",
        "meaning": "Um usuário ou sistema pode fazer praticamente tudo, como uma chave que abre todas as portas do prédio.",
        "impact": "Se esse acesso for roubado ou usado por engano, o estrago pode alcançar todo o ambiente.",
        "action": "Limitar cada acesso apenas ao que ele realmente precisa fazer.",
    },
    "site_not_secure": {
        "title": "O site não usa conexão segura",
        "meaning": "As informações trafegam sem o cadeado do navegador, o que permite que sejam lidas no caminho.",
        "impact": "Senhas e dados dos usuários podem ser interceptados, e os navegadores podem mostrar um aviso de site inseguro.",
        "action": "Ativar a conexão segura (HTTPS) em todos os endereços públicos.",
    },
}

# Varias regras tecnicas podem significar o mesmo problema para o cliente.
FINDING_TO_RISK = {
    "sg_admin_open": "admin_access_open",
    "sg_port_open": "port_open",
    "sg_missing": "network_rules_missing",
    "sg_egress_open": "outbound_open",
    "s3_public_acl": "files_public",
    "s3_no_public_block": "files_public_guard_missing",
    "s3_unencrypted": "files_unencrypted",
    "rds_unencrypted": "database_unencrypted",
    "rds_public": "database_public",
    "rds_no_backup": "database_no_backup",
    "rds_no_multi_az": "database_single_location",
    "rds_single_az": "database_single_location",
    "alb_single_az": "traffic_single_location",
    "no_cloudtrail": "no_activity_log",
    "no_config": "no_config_tracking",
    "no_cloudwatch": "no_monitoring",
    "cloudwatch_partial": "partial_monitoring",
    "iam_wildcard_action": "permissions_too_wide",
    "iam_wildcard_resource": "permissions_too_wide",
    "elb_http_only": "site_not_secure",
    "alb_no_https": "site_not_secure",
}

# status "opportunity": ainda da para economizar. "in_use": o Terraform ja faz isso.
SAVINGS: Dict[str, Dict[str, str]] = {
    "migrate_graviton": {
        "title": "Trocar os servidores por um modelo mais barato",
        "explanation": "Existem servidores equivalentes que custam menos pelo mesmo trabalho. A troca precisa de um teste antes, para confirmar que o sistema funciona neles.",
    },
    "graviton": {
        "title": "Usa servidores mais econômicos",
        "explanation": "O ambiente já usa um modelo de servidor com bom custo-benefício.",
    },
    "spot": {
        "title": "Usa capacidade com desconto",
        "explanation": "Parte do trabalho roda em capacidade mais barata, que serve bem para tarefas que podem ser interrompidas.",
    },
    "cloudfront": {
        "title": "Entrega o conteúdo mais perto dos usuários",
        "explanation": "O site guarda cópias próximas dos visitantes, o que deixa tudo mais rápido e reduz custos de transferência.",
    },
    "s3_tiering": {
        "title": "Move arquivos pouco usados para um armazenamento mais barato",
        "explanation": "Os arquivos são reorganizados automaticamente conforme o uso, sem trabalho manual.",
    },
    "s3_lifecycle": {
        "title": "Arquiva arquivos antigos automaticamente",
        "explanation": "O que não é mais usado vai para um armazenamento de baixo custo depois de um tempo.",
    },
}

ASSESSMENT = {
    "good": ("Em boa forma", "good"),
    "ok": ("Boa, com pontos a resolver", "mid"),
    "mid": ("Pede ajustes", "mid"),
    "bad": ("Precisa de atenção", "bad"),
    "unknown": ("Análise limitada", "neutral"),
}


def _group_risks(findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Agrupa regras tecnicas no mesmo risco e ordena do mais urgente ao menos urgente."""
    grouped: Dict[str, Dict[str, Any]] = {}
    for finding in findings:
        risk_id = FINDING_TO_RISK.get(finding.get("code", ""))
        if risk_id is None:
            continue
        priority = SEVERITY_PRIORITY.get(str(finding.get("severity", "")).upper(), 3)
        entry = grouped.setdefault(risk_id, {"priority": priority, "occurrences": 0})
        entry["priority"] = min(entry["priority"], priority)
        entry["occurrences"] += 1

    risks = []
    for risk_id, entry in grouped.items():
        copy = RISKS[risk_id]
        risks.append({
            "id": risk_id,
            "priority": entry["priority"],
            "priority_label": PRIORITY_LABEL[entry["priority"]],
            "occurrences": entry["occurrences"],
            "title": copy["title"],
            "meaning": copy["meaning"],
            "impact": copy["impact"],
            "action": copy["action"],
        })
    risks.sort(key=lambda r: (r["priority"], -r["occurrences"], r["title"]))
    return risks


def _split_savings(optimizations: List[Dict[str, Any]]) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    opportunities, in_use = [], []
    for item in optimizations:
        copy = SAVINGS.get(item.get("code", ""))
        if copy is None:
            continue
        target = opportunities if item.get("status") == "opportunity" else in_use
        target.append(dict(copy))
    return opportunities, in_use


def _assess(score: int, risks: List[Dict[str, Any]], recognized: bool) -> str:
    if not recognized:
        return "unknown"
    urgent = any(r["priority"] == 1 for r in risks)
    if score >= 75:
        return "ok" if urgent else "good"
    return "mid" if score >= 50 else "bad"


def _plural(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def _summary(assessment: str, score: int, risks: List[Dict[str, Any]], opportunities: List[Dict[str, str]]) -> str:
    if assessment == "unknown":
        return (
            "Não encontramos no material enviado os componentes que sabemos avaliar, "
            "então esta nota não representa o sistema real."
        )

    urgent = sum(1 for r in risks if r["priority"] == 1)
    parts = [f"O ambiente recebeu nota {score} de 100."]
    if not risks:
        parts.append("Não encontramos problemas nas verificações feitas.")
    elif urgent:
        parts.append(
            f"Encontramos {_plural(len(risks), 'ponto de melhoria', 'pontos de melhoria')}, "
            f"e {_plural(urgent, 'deles merece', 'deles merecem')} prioridade."
        )
    else:
        parts.append(
            f"Encontramos {_plural(len(risks), 'ponto de melhoria', 'pontos de melhoria')}, "
            "nenhum deles com prioridade máxima."
        )
    if opportunities:
        parts.append(f"Também há {_plural(len(opportunities), 'chance', 'chances')} de reduzir custos.")
    return " ".join(parts)


def _next_steps(assessment: str, risks: List[Dict[str, Any]], opportunities: List[Dict[str, str]]) -> List[str]:
    if assessment == "unknown":
        return [
            "Pedir à equipe técnica os arquivos de infraestrutura (Terraform) do sistema.",
            "Fazer uma nova análise com esses arquivos para receber um resultado real.",
        ]

    steps = []
    urgent = [r for r in risks if r["priority"] == 1]
    if urgent:
        steps.append(
            "Enviar este relatório à equipe técnica e combinar um prazo para o que está marcado como “Resolver primeiro”."
        )
    elif risks:
        steps.append("Enviar este relatório à equipe técnica e incluir os ajustes no planejamento das próximas semanas.")
    if opportunities:
        steps.append("Pedir uma estimativa de quanto a redução de custos representa na fatura mensal.")
    if risks:
        steps.append("Depois dos ajustes, fazer uma nova análise para confirmar a melhora da nota.")
    else:
        steps.append("Repetir esta análise sempre que a infraestrutura mudar.")
    return steps


def _as_text(report: Dict[str, Any]) -> str:
    """Versao em texto corrido, pronta para colar em um e-mail para o cliente."""
    lines = ["Resultado da análise do seu ambiente na nuvem", "", report["headline"], report["summary"]]

    if report["risks"]:
        lines += ["", "O que encontramos"]
        for risk in report["risks"]:
            lines += [
                "",
                f"{risk['priority_label']}: {risk['title']}",
                f"O que significa: {risk['meaning']}",
                f"O que pode acontecer: {risk['impact']}",
                f"O que fazer: {risk['action']}",
            ]

    if report["savings"]:
        lines += ["", "Onde dá para economizar"]
        lines += [f"- {s['title']}: {s['explanation']}" for s in report["savings"]]

    if report["strengths"]:
        lines += ["", "O que já está bem feito"]
        lines += [f"- {s['title']}: {s['explanation']}" for s in report["strengths"]]

    lines += ["", "Próximos passos"]
    lines += [f"{i}. {step}" for i, step in enumerate(report["next_steps"], 1)]
    lines += ["", report["disclaimer"]]
    return "\n".join(lines)


def build_client_report(
    score: int,
    findings: List[Dict[str, Any]],
    optimizations: List[Dict[str, Any]],
    services: List[str],
) -> Dict[str, Any]:
    recognized = any(s != "GENERAL_AWS" for s in services)
    risks = _group_risks(findings) if recognized else []
    opportunities, in_use = _split_savings(optimizations)
    assessment = _assess(score, risks, recognized)
    headline, tone = ASSESSMENT[assessment]

    report: Dict[str, Any] = {
        "headline": headline,
        "tone": tone,
        "summary": _summary(assessment, score, risks, opportunities),
        "risks": risks,
        "savings": opportunities,
        "strengths": in_use,
        "next_steps": _next_steps(assessment, risks, opportunities),
        "disclaimer": (
            "Esta análise lê a configuração enviada e não testa o sistema em funcionamento. "
            "A equipe técnica deve confirmar cada ponto antes de fazer mudanças."
        ),
    }
    report["plain_text"] = _as_text(report)
    return report
