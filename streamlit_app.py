# -*- coding: utf-8 -*-
import os  # <-- Posicionado no topo absoluto para evitar o NameError!
import streamlit as st
import pandas as pd
import base64
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection

# =========================================================================
# 1. CONFIGURAÇÃO BASE DA PÁGINA
# =========================================================================
st.set_page_config(page_title="STAHL CRM - Sistema Integrado", layout="wide", initial_sidebar_state="expanded")

# Caminhos dos arquivos físicos de mídia
CAMINHO_LOGO = "logo_stahl.png"
CAMINHO_LAYOUT_LOGIN = "layout_login.png"

# Nomes exatos das abas de texto (idênticos ao Google Sheets para evitar HTTP 400/404)
ABA_ORCAR = "Orcar"
ABA_ORCADOS = "Orcados"
ABA_PERDIDOS = "Perdidos"

# =========================================================================
# 2. CONEXÃO COM O GOOGLE SHEETS (NUVEM)
# =========================================================================
conn = st.connection("gsheets", type=GSheetsConnection)

# Inicialização segura das variáveis de sessão de login tradicionais
if 'logado' not in st.session_state: 
    st.session_state['logado'] = False
if 'user_info' not in st.session_state: 
    st.session_state['user_info'] = None
if 'bg_dinamico' not in st.session_state: 
    st.session_state['bg_dinamico'] = None
if 'mensagem_sucesso_orcar' not in st.session_state: 
    st.session_state['mensagem_sucesso_orcar'] = None
if 'mensagem_sucesso_orcados' not in st.session_state: 
    st.session_state['mensagem_sucesso_orcados'] = None
if 'exibir_dash_orcados' not in st.session_state:
    st.session_state['exibir_dash_orcados'] = False

# Filtros e controles sequenciais (Aba Orcar)
if 'filtro_orc_atual' not in st.session_state: st.session_state['filtro_orc_atual'] = []
if 'filtro_rep_atual' not in st.session_state: st.session_state['filtro_rep_atual'] = []
if 'filtro_item_atual' not in st.session_state: st.session_state['filtro_item_atual'] = []
if 'busca_empresa_atual' not in st.session_state: st.session_state['busca_empresa_atual'] = ""

# Filtros e controles sequenciais (Aba Orcados)
if 'filtro_orc_orcados' not in st.session_state: st.session_state['filtro_orc_orcados'] = []
if 'filtro_rep_orcados' not in st.session_state: st.session_state['filtro_rep_orcados'] = []
if 'filtro_item_orcados' not in st.session_state: st.session_state['filtro_item_orcados'] = []
if 'busca_empresa_orcados' not in st.session_state: st.session_state['busca_empresa_orcados'] = ""

if 'proximo_numero_orc' not in st.session_state: st.session_state['proximo_numero_orc'] = 66800

# Função auxiliar para converter imagem local em Base64 para o CSS de fundo
def obter_base64_da_imagem(caminho_arquivo):
    try:
        with open(caminho_arquivo, "rb") as f:
            dados = f.read()
        return base64.b64encode(dados).decode()
    except Exception:
        return ""

def somar_dias_uteis(data_inicio, dias):
    data_atual = data_inicio
    d_somados = 0
    while d_somados < dias:
        data_atual += timedelta(days=1)
        if data_atual.weekday() < 5: d_somados += 1
    return data_atual

# =========================================================================
# FUNÇÕES DE LEITURA E ESCRITA NA NUVEM (GOOGLE SHEETS)
# =========================================================================
def carregar_dados_da_nuvem(nome_aba, tipo="orcar"):
    try:
        df = conn.read(worksheet=nome_aba, ttl=0)
        
        # Criação blindada caso a aba esteja vazia para evitar quebras em cascata
        colunas_obrigatorias = ['IdSolicitacao', 'Situação', 'Empresa', 'Representante', 'Item', 'Orçamentista', 'ValorTotal', 'Atraso']
        if df is None or df.empty:
            return pd.DataFrame(columns=colunas_obrigatorias)
            
        df.columns = df.columns.astype(str).str.strip()
        
        mapeamento = {}
        for col in df.columns:
            col_lower = col.lower()
            if 'orçamentista' in col_lower or 'orcamentista' in col_lower: mapeamento[col] = 'Orçamentista'
            if 'idsolicitacao' in col_lower or 'id_solicitacao' in col_lower or col_lower == 'id': mapeamento[col] = 'IdSolicitacao'
            if 'situação' in col_lower or 'situacao' in col_lower or 'status' in col_lower: mapeamento[col] = 'Situação'
            if 'empresa' in col_lower or 'cliente' in col_lower: mapeamento[col] = 'Empresa'
            if 'representante' in col_lower or 'rep' in col_lower: mapeamento[col] = 'Representante'
            if 'item' in col_lower or 'equipamento' in col_lower: mapeamento[col] = 'Item'
        df = df.rename(columns=mapeamento)
        
        # Injeção segura de colunas ausentes na estrutura convertida
        for obrigatoria in colunas_obrigatorias:
            if obrigatoria not in df.columns:
                df[obrigatoria] = 0.0 if obrigatoria == 'ValorTotal' else 'None'
        
        if 'IdSolicitacao' not in df.columns and not df.empty: df['IdSolicitacao'] = range(40774, 40774 + len(df))
        if 'Situação' not in df.columns: df['Situação'] = 'Orcar' if tipo == "orcar" else 'Orcados'
        
        if 'Orçamentista' in df.columns:
            df['Orçamentista'] = df['Orçamentista'].astype(str).str.strip().str.upper().replace('NAN', 'Não Definido')
        else:
            df['Orçamentista'] = 'Não Definido'
        
        if tipo == "orcar" and not df.empty:
            if 'Orçamento' not in df.columns: df['Orçamento'] = 'None'
            
            hoje = datetime.today().date()
            atrasos_calculados = []
            for idx, row in df.iterrows():
                try:
                    if 'Previsto' in df.columns and pd.notna(row['Previsto']) and str(row['Previsto']) != 'None':
                        data_prev_str = str(row['Previsto']).split(' ')[0]
                        if '/' in data_prev_str: data_prev = datetime.strptime(data_prev_str, '%d/%m/%Y').date()
                        else: data_prev = pd.to_datetime(data_prev_str).date()
                        
                        if hoje > data_prev:
                            atrasos_calculados.append(f"{(hoje - data_prev).days} dias")
                        else: atrasos_calculados.append("No prazo")
                    else:
                        atrasos_calculados.append("No prazo")
                except Exception: atrasos_calculados.append("No prazo")
            df['Atraso'] = atrasos_calculados

        if tipo == "orcados" and not df.empty:
            if 'Solicitação de Revisão' not in df.columns: df['Solicitação de Revisão'] = 'None'
            if 'Prazo Envio Revisão' not in df.columns: df['Prazo Envio Revisão'] = 'None'

        for col in df.columns:
            if col in ['Solicitado', 'Previsto', 'Iníciado', 'Enviado', 'Solicitação de Revisão', 'Prazo Envio Revisão']:
                df[col] = df[col].astype(str).str.replace(' 00:00:00', '', regex=False).replace('nan', 'None').replace('NaT', 'None')
        return df
    except Exception as e: 
        st.error(f"Erro ao processar dados da nuvem ({nome_aba}): {e}")
        return pd.DataFrame(columns=['IdSolicitacao', 'Situação', 'Empresa', 'Representante', 'Item', 'Orçamentista', 'ValorTotal', 'Atraso'])

def salvar_dados_na_nuvem(df, nome_aba):
    try:
        conn.update(worksheet=nome_aba, data=df)
    except Exception as e:
        st.error(f"Erro crítico ao salvar dados no Google Sheets: {e}")

# Leitura inicial das bases de dados (Direto da Nuvem)
if 'df_orcar' not in st.session_state or st.session_state['df_orcar'].empty:
    st.session_state['df_orcar'] = carregar_dados_da_nuvem(ABA_ORCAR, "orcar")
if 'df_orcados' not in st.session_state or st.session_state['df_orcados'].empty:
    st.session_state['df_orcados'] = carregar_dados_da_nuvem(ABA_ORCADOS, "orcados")
if 'df_perdidos' not in st.session_state or st.session_state['df_perdidos'].empty:
    st.session_state['df_perdidos'] = carregar_dados_da_nuvem(ABA_PERDIDOS, "perdidos")

# --- CARREGAMENTO DO BACKGROUND ---
if not st.session_state['logado']:
    if not st.session_state['bg_dinamico'] and os.path.exists(CAMINHO_LAYOUT_LOGIN):
        try: st.session_state['bg_dinamico'] = obter_base64_da_imagem(CAMINHO_LAYOUT_LOGIN)
        except Exception: pass

    if st.session_state['bg_dinamico']:
        html_bg = f"""
        <div style="position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
            background-image: url('data:image/png;base64,{st.session_state['bg_dinamico']}');
            background-size: cover; background-position: center center; background-repeat: no-repeat; z-index: -1;">
        </div>
        """
        st.markdown(html_bg, unsafe_allow_html=True)

# --- CUSTOMIZAÇÃO VISUAL COMPLEMENTAR VIA CSS ---
estilo_css = """
    <style>
        """ + ("""
        .stApp, [data-testid="stApp"], [data-testid="stAppViewContainer"], [data-testid="stHeader"], .main {
            background-color: transparent !important; background-image: none !important;
        }
        """ if not st.session_state['logado'] else """
        .stApp, [data-testid="stApp"], [data-testid="stAppViewContainer"] { background-color: #F8F9FA !important; background-image: none !important; }
        .main { background-color: #F8F9FA !important; }
        """) + """
        h1, h2, h3, .section-header { color: #00205B !important; font-family: sans-serif; font-weight: 700; }
        [data-testid="stSidebar"] { background-color: #00205B !important; box-shadow: 4px 0px 10px rgba(0,0,0,0.3); }
        [data-testid="stSidebar"] .stMarkdown, [data-testid="stSidebar"] p, [data-testid="stSidebar"] span { color: #FFFFFF !important; font-size: 14px !important; }
        [data-testid="stSidebar"] input { color: #000000 !important; font-weight: 500 !important; }
        .main .block-container { padding-bottom: 40px !important; padding-top: 20px !important; }
        .section-header { font-size: 14px; border-bottom: 2px solid #00205B; padding-bottom: 3px; margin-top: 20px; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.5px; }
        
        div.stButton > button:first-child {
            background-color: #FFB800 !important; color: #00205B !important; font-size: 16px !important;
            font-weight: bold !important; border-radius: 8px !important; border: 2px solid #FFB800 !important;
            width: 100% !important; padding: 10px 20px !important; transition: all 0.3s ease !important; box-shadow: 0px 4px 6px rgba(0,0,0,0.2) !important;
        }
        div.stButton > button:first-child:hover { background-color: #FFFFFF !important; color: #00205B !important; border: 2px solid #FFFFFF !important; transform: scale(1.02); }
        
        .metric-card {
            background-color: #FFFFFF;
            padding: 15px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            border-left: 5px solid #00205B;
            text-align: center;
        }
    </style>
"""
st.markdown(estilo_css, unsafe_allow_html=True)

EQUIPAMENTOS_DB = {
    "Complemento Of": 2, "Componentes": 5, "Estimativa": 4, "Guindaste Especial": 5, 
    "Guindaste Giratório": 5, "Guindaste Smalljib": 5, "Monovia": 5, "Pacote de Equipamentos": 10,
    "Pacote de Pontes": 7, "Pacote de Talhas": 5, "Ponte Rolante Duobox": 7, "Ponte Rolante Monobox": 7,
    "Ponte Rolante Smallcrane": 7, "Pórtico Manual": 7, "Pórtico Rolante": 10, "Sistema Modular Lcs": 5,
    "Talha Elétrica de Cabo Top Lift": 5, "Talha Elétrica de Cabo Scs": 5, "Talha Elétrica de Corrente Scs": 2,
    "Talha Elétrica de Corrente Top Lift": 2
}
ESTADOS_BR = ["SP", "PR", "MG", "BA", "RJ", "SC", "RS", "PE", "AM", "RN", "PB", "GO", "DF", "ES", "CE"]
LISTA_REPRESENTANTES = ["Meire Queiroz", "Fernando H. Junior", "Eng° Julio Correia", "Eng° Gustavo Swenson", "Daniela Santana", "Eng° Darilton Aguiar", "Haroldo Rezende", "Bruno Castro", "Eng° Mauro Reich", "Eng° Jacson Voit", "Eng° Ozias Winckler", "Ronaldo Silva", "Basílio Oliveira", "S/rep"]
LISTA_ORCAMENTISTAS_CADASTRO = ["LF", "RS", "JV", "REP", "Não Definido"]

# =========================================================================
# BANCO DE DADOS DE USUÁRIOS E REGRAS DE SEGURANÇA
# =========================================================================
USUARIOS_DB = {
    "thamires": {
        "nome": "Thamires Martins", 
        "sigla": "TM", 
        "perfil": "administrador",
        "senha": "stahl@2026"
    }
}

# =========================================================================
# BARRA LATERAL
# =========================================================================
with st.sidebar:
    if os.path.exists(CAMINHO_LOGO): 
        st.image(CAMINHO_LOGO, use_container_width=True)
    else: 
        st.markdown("<div style='font-size:20px; font-weight:800; color:#FFB800; text-align:center; padding:10px;'>⚡ STAHL CRM</div>", unsafe_allow_html=True)
    st.markdown("<hr style='margin:15px 0; border-color: rgba(255,255,255,0.15);'>", unsafe_allow_html=True)

# --- TELA DE LOGIN ---
if not st.session_state['logado']:
    st.sidebar.markdown("<div style='text-align: center; margin-bottom: 20px;'><span style='font-size: 32px;'>🔒</span><div style='font-size: 15px; font-weight: 700; color: #FFB800; letter-spacing: 2px; margin-top: 5px;'>ACESSO</div></div>", unsafe_allow_html=True)
    usuario_input = st.sidebar.text_input("Login do usuário:")
    senha_input = st.sidebar.text_input("Senha corporativa:", type="password")
    botao_entrar = st.sidebar.button("Entrar no Sistema")

    if botao_entrar:
        usr = usuario_input.strip().lower()
        if usr in USUARIOS_DB and senha_input == USUARIOS_DB[usr]["senha"]:
            st.session_state['logado'] = True
            st.session_state['user_info'] = USUARIOS_DB[usr]
            st.rerun()
        else: 
            st.sidebar.error("Usuário ou senha incorretos.")

# --- INTERFACE PRINCIPAL (SÓ ABRE SE LOGADO) ---
if st.session_state['logado']:
    user_info = st.session_state['user_info']
    st.sidebar.success(f"Conectado: {user_info['nome']}")
    menu = st.sidebar.radio("Navegação Administrador:", ["➕ Cadastrar Solicitação", "📁 Visão Geral das Bases", "⚙️ Configurações"])

    if st.sidebar.button("Sair / Desconectar"):
        st.session_state['logado'] = False
        st.session_state['user_info'] = None
        st.rerun()

    # --- TELA DE CADASTRO ---
    if menu == "➕ Cadastrar Solicitação":
        st.subheader("📝 Cadastro de Nova Proposta Comercial")
        
        if st.session_state['mensagem_sucesso_orcar']:
            st.success(st.session_state['mensagem_sucesso_orcar'], icon="🚀")
            if st.button("Fechar Alerta ❌", key="close_cad"):
                st.session_state['mensagem_sucesso_orcar'] = None
                st.rerun()

        st.markdown("<div class='section-header'>Dados do Cliente e Localidade</div>", unsafe_allow_html=True)
        c1, c2, c3 = st.columns([2, 1, 1])
        with c1: empresa_sol = st.text_input("Razão Social da Empresa / Cliente:")
        with c2: cidade_sol = st.text_input("Cidade:")
        with c3: uf_sol = st.selectbox("UF do Destino:", ESTADOS_BR)
            
        cc1, cc2, cc3 = st.columns(3)
        with cc1: contato_nome = st.text_input("Nome do Contato Principal:")
        with cc2: contato_tel = st.text_input("Telefone de Contato:")
        with cc3: contato_email = st.text_input("E-mail do Cliente:")

        st.markdown("<br>", unsafe_allow_html=True)
        c7, c8, c9 = st.columns([2, 1, 1])
        with c7:
            eq_sol = st.selectbox("Equipamento Stahl:", list(EQUIPAMENTOS_DB.keys()))
            prazo_dias = EQUIPAMENTOS_DB[eq_sol]
        with c8: qtde_sol = st.number_input("Quantidade:", min_value=1, value=1)
        with c9: orc_resp = st.selectbox("Orçamentista Designado (Sigla):", LISTA_ORCAMENTISTAS_CADASTRO)

        rep_vinculado_automatico = "S/rep"
        if orc_resp == "REP":
            rep_vinculado_automatico = st.selectbox("Qual representative está orçando?:", [r for r in LISTA_REPRESENTANTES if r != "S/rep"])

        st.markdown("<br>", unsafe_allow_html=True)
        c4, c5, c6 = st.columns(3)
        with c4: data_sol = st.date_input("Data de Entrada / Solicitação:", datetime.today().date())
        with c5:
            prazo_sugerido = somar_dias_uteis(data_sol, prazo_dias)
            previsao_entrega = st.date_input("Previsão de Entrega Técnica:", prazo_sugerido)
        
        with c6:
            index_default_rep = 0
            if orc_resp == "REP":
                if rep_vinculado_automatico in LISTA_REPRESENTANTES: index_default_rep = LISTA_REPRESENTANTES.index(rep_vinculado_automatico)
            else:
                for i, rep_nome in enumerate(LISTA_REPRESENTANTES):
                    if orc_resp.lower() in rep_nome.lower() and orc_resp != "Não Definido":
                        index_default_rep = i
                        break
            rep_sol = st.selectbox("Representante Comercial Responsável:", LISTA_REPRESENTANTES, index=index_default_rep)

        obs_sol = st.text_area("Observações Iniciais do Atendimento:")
        
        if st.button("Gravar Solicitação no Banco de Dados 🚀"):
            if not empresa_sol.strip(): st.error("Por favor, preencha a Razão Social da Empresa.")
            else:
                df_atual = carregar_dados_da_nuvem(ABA_ORCAR, "orcar")
                proximo_id = int(pd.to_numeric(df_atual['IdSolicitacao'], errors='coerce').max()) + 1 if not df_atual.empty and 'IdSolicitacao' in df_atual.columns else 40774
                
                nova_linha = {
                    "IdSolicitacao": proximo_id, "Situação": "Orcar", "Atraso": "No prazo",
                    "Empresa": empresa_sol.strip().upper(), "Representante": rep_sol,
                    "Solicitado": data_sol.strftime('%d/%m/%Y'), "Previsto": previsao_entrega.strftime('%d/%m/%Y'),
                    "Iníciado": "None", "Orçamentista": str(orc_resp).strip().upper(),
                    "Orçamento": "None", "Rev": 0, "Enviado": "None",
                    "Item": eq_sol, "Qtde": qtde_sol, "Observação": obs_sol.strip(),
                    "Fone": contato_tel, "UF": str(uf_sol).strip().upper(),
                    "Cidade": cidade_sol, "Contato": contato_nome, "ValorTotal": 0.0
                }
                
                df_final = pd.concat([df_atual, pd.DataFrame([nova_linha])], ignore_index=True)
                
                salvar_dados_na_nuvem(df_final, ABA_ORCAR)
                
                st.session_state['df_orcar'] = df_final
                st.session_state['mensagem_sucesso_orcar'] = f"✅ Gravado com Sucesso na Nuvem! ID: {proximo_id}"
                st.rerun()

    # --- TELA DE VISÃO GERAL ---
    elif menu == "📁 Visão Geral das Bases":
        st.subheader("📁 Gerenciamento de propostas")
        
        if st.session_state['mensagem_sucesso_orcar']:
            st.success(st.session_state['mensagem_sucesso_orcar'], icon="✅")

        aba_orcar_tab, aba_orcados_tab, aba_perdidos_tab = st.tabs(["⏳ 1. Base ORCAR / ORCANDO", "✅ 2. Base ORCADOS", "❌ 3. Base PERDIDOS"])
        
        # ABA 1: BASE ORCAR / ORCANDO
        with aba_orcar_tab:
            st.markdown("<div class='section-header'>🔍 Filtro</div>", unsafe_allow_html=True)
            f1, f2, f3 = st.columns(3)
            with f1:
                try:
                    if 'df_orcar' in st.session_state and not st.session_state['df_orcar'].empty and 'Orçamentista' in st.session_state['df_orcar'].columns:
                        opcoes_orc = sorted([str(x).upper().strip() for x in st.session_state['df_orcar']['Orçamentista'].dropna().unique() if str(x).lower() != 'nan'])
                    else: opcoes_orc = []
                except Exception: opcoes_orc = []
                st.session_state['filtro_orc_atual'] = st.multiselect("Filtrar por Orçamentista:", opcoes_orc, default=st.session_state['filtro_orc_atual'], placeholder="Selecione as opções...")
            with f2:
                try:
                    if 'df_orcar' in st.session_state and not st.session_state['df_orcar'].empty and 'Representante' in st.session_state['df_orcar'].columns:
                        opcoes_rep = sorted([str(x).strip() for x in st.session_state['df_orcar']['Representante'].dropna().unique() if str(x).lower() != 'nan'])
                    else: opcoes_rep = []
                except Exception: opcoes_rep = []
                st.session_state['filtro_rep_atual'] = st.multiselect("Filtrar por Representante:", opcoes_rep, default=st.session_state['filtro_rep_atual'], placeholder="Selecione as opções...")
            with f3:
                try:
                    if 'df_orcar' in st.session_state and not st.session_state['df_orcar'].empty and 'Item' in st.session_state['df_orcar'].columns:
                        opcoes_item = sorted([str(x).strip() for x in st.session_state['df_orcar']['Item'].dropna().unique() if str(x).lower() != 'nan'])
                    else: opcoes_item = []
                except Exception: opcoes_item = []
                st.session_state['filtro_item_atual'] = st.multiselect("Filtrar por Item:", opcoes_item, default=st.session_state['filtro_item_atual'], placeholder="Selecione as opções...")
                
            st.session_state['busca_empresa_atual'] = st.text_input("⌨️ Pesquisar Empresa:", value=st.session_state['busca_empresa_atual'])
            
            df_orcar_filtrado = st.session_state['df_orcar'].copy() if 'df_orcar' in st.session_state and not st.session_state['df_orcar'].empty else pd.DataFrame([])
            
            if not df_orcar_filtrado.empty:
                if st.session_state['filtro_orc_atual'] and 'Orçamentista' in df_orcar_filtrado.columns: 
                    df_orcar_filtrado = df_orcar_filtrado[df_orcar_filtrado['Orçamentista'].astype(str).str.upper().str.strip().isin(st.session_state['filtro_orc_atual'])]
                if st.session_state['filtro_rep_atual'] and 'Representante' in df_orcar_filtrado.columns: 
                    df_orcar_filtrado = df_orcar_filtrado[df_orcar_filtrado['Representante'].astype(str).str.strip().isin(st.session_state['filtro_rep_atual'])]
                if st.session_state['filtro_item_atual'] and 'Item' in df_orcar_filtrado.columns: 
                    df_orcar_filtrado = df_orcar_filtrado[df_orcar_filtrado['Item'].astype(str).str.strip().isin(st.session_state['filtro_item_atual'])]
                if st.session_state['busca_empresa_atual'] and 'Empresa' in df_orcar_filtrado.columns: 
                    df_orcar_filtrado = df_orcar_filtrado[df_orcar_filtrado['Empresa'].astype(str).str.contains(st.session_state['busca_empresa_atual'], case=False, na=False)]
            
            st.markdown("<div class='section-header'>⚙️ Ações</div>", unsafe_allow_html=True)
            
            if not df_orcar_filtrado.empty:
                if "Selecionar" not in df_orcar_filtrado.columns:
                    df_orcar_filtrado.insert(0, "Selecionar", False)
                act1, act2, act3 = st.columns(3)
                
                df_editado = st.data_editor(
                    df_orcar_filtrado,
                    key="editor_orcar_real",
                    hide_index=True,
                    use_container_width=True,
                    disabled=[c for c in df_orcar_filtrado.columns if c in ["IdSolicitacao", "Situação", "Atraso", "Solicitado", "Previsto"]]
                )
                
                # CORREÇÃO DA DIGITAÇÃO: Corrigido e validado para português limpo
                linhas_selecionadas = df_editado[df_editado["Selecionar"] == True]
                
                with act1:
                    if st.button("🚀 Iniciar"):
                        if not linhas_selecionadas.empty:
                            num_atual = int(st.session_state['proximo_numero_orc'])
                            lista_numeros_gerados = []
                            for idx, row in linhas_selecionadas.iterrows():
                                id_sol = row["IdSolicitacao"]
                                num_orc = f"ORC-26-{num_atual:06d}"
                                lista_numeros_gerados.append(num_orc)
                                st.session_state['df_orcar'].loc[st.session_state['df_orcar']['IdSolicitacao'] == id_sol, 'Situação'] = 'Orcando'
                                st.session_state['df_orcar'].loc[st.session_state['df_orcar']['IdSolicitacao'] == id_sol, 'Orçamento'] = num_orc
                                st.session_state['df_orcar'].loc[st.session_state['df_orcar']['IdSolicitacao'] == id_sol, 'Iníciado'] = datetime.today().strftime('%d/%m/%Y')
                                num_atual += 1
                            st.session_state['proximo_numero_orc'] = num_atual
                            
                            salvar_dados_na_nuvem(st.session_state['df_orcar'], ABA_ORCAR)
                            st.session_state['mensagem_sucesso_orcar'] = f"Orçamento Iniciado na Nuvem! {', '.join(lista_numeros_gerados)}"
                            st.rerun()
                        else: st.warning("Selecione um registro na caixinha.")
                        
                with act2:
                    if st.button("💾 Salvar Edições da Tabela"):
                        for idx, row in df_editado.iterrows():
                            id_sol = row["IdSolicitacao"]
                            for col in [c for c in df_editado.columns if c not in ["Selecionar"]]:
                                val = row[col]
                                if col == 'Orçamentista': val = str(val).strip().upper()
                                st.session_state['df_orcar'].loc[st.session_state['df_orcar']['IdSolicitacao'] == id_sol, col] = val
                        
                        salvar_dados_na_nuvem(st.session_state['df_orcar'], ABA_ORCAR)
                        st.session_state['mensagem_sucesso_orcar'] = "Alterações salvas com sucesso no Google Sheets!"
                        st.rerun()
                        
                with act3:
                    if st.button("📨 Enviar Orçamento"):
                        if not linhas_selecionadas.empty:
                            indices_para_remover = []
                            for idx, row in linhas_selecionadas.iterrows():
                                id_sol = row["IdSolicitacao"]
                                registro_original = st.session_state['df_orcar'][st.session_state['df_orcar']['IdSolicitacao'] == id_sol]
                                if not registro_original.empty:
                                    reg = registro_original.iloc[0].to_dict()
                                    reg['Situação'] = 'Orcados'
                                    reg['ValorTotal'] = row['ValorTotal']
                                    reg['Orçamento'] = row['Orçamento']
                                    reg['Enviado'] = datetime.today().strftime('%d/%m/%Y')
                                    reg['Solicitação de Revisão'] = 'None'
                                    reg['Prazo Envio Revisão'] = 'None'
                                    st.session_state['df_orcados'] = pd.concat([st.session_state['df_orcados'], pd.DataFrame([reg])], ignore_index=True)
                                    indices_para_remover.append(id_sol)
                            st.session_state['df_orcar'] = st.session_state['df_orcar'][~st.session_state['df_orcar']['IdSolicitacao'].isin(indices_para_remover)]
                            
                            salvar_dados_na_nuvem(st.session_state['df_orcar'], ABA_ORCAR)
                            salvar_dados_na_nuvem(st.session_state['df_orcados'], ABA_ORCADOS)
                            
                            st.session_state['mensagem_sucesso_orcar'] = "Transferido para a base de Orçados na Nuvem com sucesso!"
                            st.rerun()
                        else: st.warning("Selecione um registro na caixinha.")

        # ABA 2: BASE ORÇADOS 
        with aba_orcados_tab:
            if st.session_state['mensagem_sucesso_orcados']:
                st.success(st.session_state['mensagem_sucesso_orcados'], icon="✅")
                st.session_state['mensagem_sucesso_orcados'] = None

            df_orcados_raw = st.session_state['df_orcados'].copy() if 'df_orcados' in st.session_state and not st.session_state['df_orcados'].empty else pd.DataFrame([])

            st.markdown("<div class='section-header'>🔍 Filtros da Carteira de Orçados</div>", unsafe_allow_html=True)
            fo1, fo2, fo3 = st.columns(3)
            with fo1:
                try:
                    opcoes_orc_o = sorted([str(x).upper().strip() for x in df_orcados_raw['Orçamentista'].dropna().unique() if str(x).lower() != 'nan']) if not df_orcados_raw.empty else []
                except Exception: opcoes_orc_o = []
                st.session_state['filtro_orc_orcados'] = st.multiselect("Filtrar por Orçamentista (Orçados):", opcoes_orc_o, default=st.session_state['filtro_orc_orcados'], placeholder="Selecione os orçamentistas...", key="mult_orc_o")
            with fo2:
                try:
                    opcoes_rep_o = sorted([str(x).strip() for x in df_orcados_raw['Representante'].dropna().unique() if str(x).lower() != 'nan']) if not df_orcados_raw.empty else []
                except Exception: opcoes_rep_o = []
                st.session_state['filtro_rep_orcados'] = st.multiselect("Filtrar por Representante (Orçados):", opcoes_rep_o, default=st.session_state['filtro_rep_orcados'], placeholder="Selecione os representantes...", key="mult_rep_o")
            with fo3:
                try:
                    opcoes_item_o = sorted([str(x).strip() for x in df_orcados_raw['Item'].dropna().unique() if str(x).lower() != 'nan']) if not df_orcados_raw.empty else []
                except Exception: opcoes_item_o = []
                st.session_state['filtro_item_orcados'] = st.multiselect("Filtrar por Item (Orçados):", opcoes_item_o, default=st.session_state['filtro_item_orcados'], placeholder="Selecione os itens...", key="mult_item_o")
                
            st.session_state['busca_empresa_orcados'] = st.text_input("⌨️ Pesquisar Empresa em Orçados:", value=st.session_state['busca_empresa_orcados'], key="txt_emp_o")

            df_orcados_filtrado = df_orcados_raw.copy()
            if not df_orcados_filtrado.empty:
                if st.session_state['filtro_orc_orcados']:
                    df_orcados_filtrado = df_orcados_filtrado[df_orcados_filtrado['Orçamentista'].astype(str).str.upper().str.strip().isin(st.session_state['filtro_orc_orcados'])]
                if st.session_state['filtro_rep_orcados']:
                    df_orcados_filtrado = df_orcados_filtrado[df_orcados_filtrado['Representante'].astype(str).str.strip().isin(st.session_state['filtro_rep_orcados'])]
                if st.session_state['filtro_item_orcados']:
                    df_orcados_filtrado = df_orcados_filtrado[df_orcados_filtrado['Item'].astype(str).str.strip().isin(st.session_state['filtro_item_orcados'])]
                if st.session_state['busca_empresa_orcados']:
                    df_orcados_filtrado = df_orcados_filtrado[df_orcados_filtrado['Empresa'].astype(str).str.contains(st.session_state['busca_empresa_orcados'], case=False, na=False)]

            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("📊 Abrir / Fechar Dashboard de Performance", key="btn_toggle_dash"):
                st.session_state['exibir_dash_orcados'] = not st.session_state['exibir_dash_orcados']
                st.rerun()

            if st.session_state['exibir_dash_orcados'] and not df_orcados_filtrado.empty:
                st.markdown("<div style='background-color: #F1F3F5; padding: 20px; border-radius: 10px; margin-bottom: 20px;'>", unsafe_allow_html=True)
                st.markdown("### 📊 Indicadores de Performance - Filtrados")
                
                c_dash1, c_dash2 = st.columns(2)
                with c_dash1:
                    data_de = st.date_input("De:", datetime.today().date() - timedelta(days=30), key="dash_dt_de")
                with c_dash2:
                    data_ate = st.date_input("Até:", datetime.today().date(), key="dash_dt_ate")

                df_dash = df_orcados_filtrado.copy()
                df_dash['Enviado_DT'] = pd.to_datetime(df_dash['Enviado'], errors='coerce').dt.date
                df_dash = df_dash[(df_dash['Enviado_DT'] >= data_de) & (df_dash['Enviado_DT'] <= data_ate)]

                if not df_dash.empty:
                    total_enviados = len(df_dash)
                    no_prazo = 0
                    antecipado = 0
                    atrasado = 0
                    
                    for idx, r in df_dash.iterrows():
                        try:
                            dt_prev_raw = pd.to_datetime(r['Previsto'], errors='coerce')
                            dt_prev = dt_prev_raw.date() if pd.notna(dt_prev_raw) else None
                            dt_env = r['Enviado_DT']
                            
                            if dt_prev and dt_env:
                                if dt_env == dt_prev: no_prazo += 1
                                elif dt_env < dt_prev: antecipado += 1
                                else: atrasado += 1
                            else: no_prazo += 1 
                        except Exception: no_prazo += 1

                    m1, m2, m3, m4 = st.columns(4)
                    with m1:
                        st.markdown(f"<div class='metric-card'><p style='color:#00205B; margin:0; font-weight:bold;'>Total Enviados</p><h2 style='margin:5px 0;'>{total_enviados}</h2><span style='font-size:12px; color:gray;'>No período filtrado</span></div>", unsafe_allow_html=True)
                    with m2:
                        pct_ant = (antecipado / total_enviados) * 100 if total_enviados > 0 else 0
                        st.markdown(f"<div class='metric-card' style='border-left-color: #28A745;'><p style='color:#28A745; margin:0; font-weight:bold;'>🚀 Antecipados</p><h2 style='margin:5px 0;'>{antecipado}</h2><span style='font-size:13px; font-weight:bold;'>{pct_ant:.1f}%</span></div>", unsafe_allow_html=True)
                    with m3:
                        pct_prazo = (no_prazo / total_enviados) * 100 if total_enviados > 0 else 0
                        st.markdown(f"<div class='metric-card' style='border-left-color: #17A2B8;'><p style='color:#17A2B8; margin:0; font-weight:bold;'>⏱️ No Prazo</p><h2 style='margin:5px 0;'>{no_prazo}</h2><span style='font-size:13px; font-weight:bold;'>{pct_prazo:.1f}%</span></div>", unsafe_allow_html=True)
                    with m4:
                        pct_atr = (atrasado / total_enviados) * 100 if total_enviados > 0 else 0
                        st.markdown(f"<div class='metric-card' style='border-left-color: #DC3545;'><p style='color:#DC3545; margin:0; font-weight:bold;'>⚠️ Atrasados</p><h2 style='margin:5px 0;'>{atrasado}</h2><span style='font-size:13px; font-weight:bold;'>{pct_atr:.1f}%</span></div>", unsafe_allow_html=True)
                else:
                    st.info("Nenhum orçamento enviado com esse critério no intervalo selecionado.")
                st.markdown("</div>", unsafe_allow_html=True)

            if not df_orcados_filtrado.empty:
                alertas = []
                for idx, row in df_orcados_filtrado.iterrows():
                    if str(row.get('Situação', '')).strip().lower() == 'em revisao':
                        alertas.append("❗ REVISÃO")
                    else: alertas.append("")
                df_orcados_filtrado.insert(0, "⚠️", alertas)

                if "Selecionar" not in df_orcados_filtrado.columns:
                    df_orcados_filtrado.insert(0, "Selecionar", False)

                st.markdown("<div class='section-header'>⚙️ Ações da Base de Orçados</div>", unsafe_allow_html=True)
                col_btn_o1, col_btn_o2 = st.columns([1, 1])
                
                df_editado_orcados = st.data_editor(
                    df_orcados_filtrado,
                    key="editor_orcados_real",
                    hide_index=True,
                    use_container_width=True,
                    disabled=[c for c in df_orcados_filtrado.columns if c in ["⚠️", "IdSolicitacao", "Situação", "Solicitado", "Previsto", "Iníciado", "Enviado", "Solicitação de Revisão", "Prazo Envio Revisão"]]
                )
                
                # CORREÇÃO DA DIGITAÇÃO: Higienizado de typos remanescentes de espanhol
                linhas_selecionadas_o = df_editado_orcados[df_editado_orcados["Selecionar"] == True]

                with col_btn_o1:
                    if st.button("🔄 Abrir Revisão de Proposta", key="btn_abrir_rev"):
                        if not linhas_selecionadas_o.empty:
                            hoje_str = datetime.today().strftime('%d/%m/%Y')
                            prazo_rev_str = somar_dias_uteis(datetime.today(), 2).strftime('%d/%m/%Y')
                            
                            for idx, row in linhas_selecionadas_o.iterrows():
                                id_sol = row["IdSolicitacao"]
                                st.session_state['df_orcados'].loc[st.session_state['df_orcados']['IdSolicitacao'] == id_sol, 'Situação'] = 'Em Revisao'
                                st.session_state['df_orcados'].loc[st.session_state['df_orcados']['IdSolicitacao'] == id_sol, 'Solicitação de Revisão'] = hoje_str
                                st.session_state['df_orcados'].loc[st.session_state['df_orcados']['IdSolicitacao'] == id_sol, 'Prazo Envio Revisão'] = prazo_rev_str
                                
                            salvar_dados_na_nuvem(st.session_state['df_orcados'], ABA_ORCADOS)
                            st.session_state['mensagem_sucesso_orcados'] = f"Revisão aberta com sucesso na nuvem! Prazo de envio: {prazo_rev_str}"
                            st.rerun()
                        else: st.warning("Selecione um orçamento na caixinha para abrir a revisão.")

                with col_btn_o2:
                    if st.button("💾 Salvar Modificações de Valores/Campos", key="btn_salvar_o"):
                        for idx, row in df_editado_orcados.iterrows():
                            id_sol = row["IdSolicitacao"]
                            for col in [c for c in df_editado_orcados.columns if c not in ["Selecionar", "⚠️"]]:
                                val = row[col]
                                st.session_state['df_orcados'].loc[st.session_state['df_orcados']['IdSolicitacao'] == id_sol, col] = val
                        
                        salvar_dados_na_nuvem(st.session_state['df_orcados'], ABA_ORCADOS)
                        st.session_state['mensagem_sucesso_orcados'] = "Alterações de Orçados salvas com sucesso na nuvem!"
                        st.rerun()
            else:
                st.info("Planilha 'Orçados' na nuvem vazia ou nenhum dado corresponde aos filtros.")

        # ABA 3: BASE PERDIDOS
        with aba_perdidos_tab:
            if 'df_perdidos' in st.session_state and not st.session_state['df_perdidos'].empty: 
                st.dataframe(st.session_state['df_perdidos'], use_container_width=True)
            else: st.info("Planilha 'Perdidos' na nuvem vazia.")

    # --- CONFIGURAÇÃO ---
    elif menu == "⚙️ Configurações":
        st.subheader("⚙️ Configurações")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("<div class='section-header'>🎛️ Parametrização</div>", unsafe_allow_html=True)
            num_ajustado = st.number_input("Próximo número sequencial:", value=int(st.session_state['proximo_numero_orc']), step=1)
            if st.button("💾 Travar Sequência"):
                st.session_state['proximo_numero_orc'] = num_ajustado
                st.success(f"Configurado para: ORC-26-{num_ajustado:06d}")
            
            st.markdown("<div class='section-header'>Upload de Identidade Visual</div>", unsafe_allow_html=True)
            upload_layout = st.file_uploader("Upload Background Login:", type=['png', 'jpg', 'jpeg'])
            if upload_layout is not None:
                bytes_data = upload_layout.getvalue()
                st.session_state['bg_dinamico'] = base64.b64encode(bytes_data).decode()  
                if st.button("💾 Salvar Layout"):
                    with open(CAMINHO_LAYOUT_LOGIN, "wb") as f: f.write(upload_layout.getbuffer())
                    st.success("Layout local atualizado!")
                    st.rerun()
                    
        with col2:
            st.markdown("<div class='section-header'>📂 Sincronização e Carga Manual Directa (Nuvem)</div>", unsafe_allow_html=True)
            st.caption("Ao fazer o upload aqui, você sobrescreve os dados atuais do Google Sheets na nuvem.")
            
            up_orcar = st.file_uploader("1. Forçar Atualização Planilha de ORÇAR:", type=['xlsx'])
            if up_orcar is not None and st.button("🚀 Enviar para o Google Sheets (Orçar)"):
                df_upload = pd.read_excel(up_orcar)
                salvar_dados_na_nuvem(df_upload, ABA_ORCAR)
                st.session_state['df_orcar'] = carregar_dados_da_nuvem(ABA_ORCAR, "orcar")
                st.success("Base activa de Orçar atualizada na nuvem!")
                st.rerun()

            up_orcados = st.file_uploader("2. Forçar Atualização Planilha de ORCADOS:", type=['xlsx'])
            if up_orcados is not None and st.button("🚀 Enviar para o Google Sheets (Orçados)"):
                df_upload = pd.read_excel(up_orcados)
                salvar_dados_na_nuvem(df_upload, ABA_ORCADOS)
                st.session_state['df_orcados'] = carregar_dados_da_nuvem(ABA_ORCADOS, "orcados")
                st.success("Base de Orçados atualizada na nuvem!")
                st.rerun()

            up_perdidos = st.file_uploader("3. Forçar Atualização Planilha de PERDIDOS:", type=['xlsx'])
            if up_perdidos is not None and st.button("🚀 Enviar para o Google Sheets (Perdidos)"):
                df_upload = pd.read_excel(up_perdidos)
                salvar_dados_na_nuvem(df_upload, ABA_PERDIDOS)
                st.session_state['df_perdidos'] = carregar_dados_da_nuvem(ABA_PERDIDOS, "perdidos")
                st.success("Base de Perdidos atualizada na nuvem!")
                st.rerun()