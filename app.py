import streamlit as st
import pandas as pd
import pdfplumber
import re
from io import BytesIO

# Configuração da página
st.set_page_config(page_title="Conciliador de Mensalidades - PAX", layout="wide")

st.title("📊 Conciliação de Contas a Receber")
st.markdown("""
Faça o upload dos arquivos de **Recebidos** e **A Receber** para realizar a conciliação automática.
O sistema filtrará os dados com base no mês de vencimento selecionado.
""")

def extract_data_from_pdf(uploaded_files):
    """Extrai dados dos PDFs e retorna uma lista de strings por linha."""
    all_rows = []
    
    for uploaded_file in uploaded_files:
        with pdfplumber.open(uploaded_file) as pdf:
            for page in pdf.pages:
                table = page.extract_table()
                if table:
                    for row in table:
                        # CORREÇÃO: Converte cada item para string, tratando None/NaN como string vazia
                        clean_row = [str(item) if item is not None else "" for item in row]
                        # Filtra linhas que são totalmente vazias
                        if any(clean_row):
                            all_rows.append(clean_row)
    return all_rows

def preprocess_receber(rows):
    """Tratamento específico para arquivos 'A Receber'."""
    new_rows = []
    for row in rows:
        row_str = " ".join(row) # Agora garantido que todos são strings
        
        # Regex ajustada para o padrão dos seus arquivos
        # Procura Contrato (números isolados), Data e Valor no final
        contrato = re.search(r'\b(\d{3,5})\b', row_str) 
        data = re.search(r'(\d{2}/\d{2}/\d{4})', row_str)
        valor = re.search(r'(\d+,\d{2})$', row_str.strip()) # Valor costuma estar no fim da linha
        
        if contrato and data and valor:
            try:
                val_float = float(valor.group(1).replace('.', '').replace(',', '.'))
                new_rows.append({
                    'Contrato': contrato.group(1),
                    'Data_Vencto': pd.to_datetime(data.group(1), dayfirst=True),
                    'Valor_Previsto': val_float,
                    'Linha_Original': row_str[:50] + "..." # Para auditoria se necessário
                })
            except:
                continue
    return pd.DataFrame(new_rows)

def preprocess_recebidos(rows):
    """Tratamento específico para arquivos 'Recebidos'."""
    new_rows = []
    for row in rows:
        row_str = " ".join(row)
        
        contrato = re.search(r'\b(\d{3,5})\b', row_str)
        # Em recebidos, pegamos a primeira data (Vencimento)
        datas = re.findall(r'(\d{2}/\d{2}/\d{4})', row_str)
        valor = re.search(r'(\d+,\d{2})$', row_str.strip())
        
        if contrato and len(datas) >= 1 and valor:
            try:
                val_float = float(valor.group(1).replace('.', '').replace(',', '.'))
                dt_venc = pd.to_datetime(datas[0], dayfirst=True)
                new_rows.append({
                    'Contrato': contrato.group(1),
                    'Mes_Venc': dt_venc.month,
                    'Ano_Venc': dt_venc.year,
                    'Valor_Pago': val_float,
                    'Status': 'Recebido'
                })
            except:
                continue
    return pd.DataFrame(new_rows)

# Interface de Upload
col1, col2 = st.columns(2)

with col1:
    st.subheader("📁 Arquivos 'A Receber'")
    files_receber = st.file_uploader("Upload (A RECEBER / EM ATRASO)", type="pdf", accept_multiple_files=True, key="receber")

with col2:
    st.subheader("📁 Arquivos 'Recebidos'")
    files_recebidos = st.file_uploader("Upload (RECEBIDAS / EM ATRASO)", type="pdf", accept_multiple_files=True, key="recebidos")

# Filtros
st.sidebar.header("Configurações")
mes_selecionado = st.sidebar.selectbox("Mês de Vencimento", range(1, 13), index=4) # Maio
ano_selecionado = st.sidebar.number_input("Ano", min_value=2024, max_value=2030, value=2026)

if st.button("🚀 Executar Conciliação"):
    if files_receber and files_recebidos:
        try:
            with st.spinner("Processando..."):
                # Extração
                rows_receber = extract_data_from_pdf(files_receber)
                rows_recebidos = extract_data_from_pdf(files_recebidos)
                
                # Transformação
                df_receber = preprocess_receber(rows_receber)
                df_recebidos = preprocess_recebidos(rows_recebidos)
                
                if df_receber.empty or df_recebidos.empty:
                    st.error("Não foi possível extrair dados válidos dos PDFs. Verifique o formato.")
                    st.stop()

                # Filtragem do Mês/Ano solicitado (foco no Vencimento do Mês)
                df_receber_mes = df_receber[
                    (df_receber['Data_Vencto'].dt.month == mes_selecionado) & 
                    (df_receber['Data_Vencto'].dt.year == ano_selecionado)
                ].copy()

                # Conciliação por Contrato E Valor (para evitar falsos positivos)
                # Removemos duplicatas de recebimento para o mesmo contrato no mesmo mês
                df_recebidos_clean = df_recebidos[
                    (df_recebidos['Mes_Venc'] == mes_selecionado) & 
                    (df_recebidos['Ano_Venc'] == ano_selecionado)
                ].drop_duplicates(subset=['Contrato'])

                conciliacao = pd.merge(
                    df_receber_mes, 
                    df_recebidos_clean[['Contrato', 'Valor_Pago', 'Status']], 
                    on='Contrato', 
                    how='left'
                )
                
                conciliacao['Status'] = conciliacao['Status'].fillna('Pendente')
                conciliacao['Valor_Pago'] = conciliacao['Valor_Pago'].fillna(0.0)

                # KPIs
                st.divider()
                kpi1, kpi2, kpi3 = st.columns(3)
                total_previsto = conciliacao['Valor_Previsto'].sum()
                total_recebido = conciliacao[conciliacao['Status'] == 'Recebido']['Valor_Previsto'].sum()
                
                kpi1.metric("Total Previsto (Venc. no Mês)", f"R$ {total_previsto:,.2f}")
                kpi2.metric("Total Conciliado", f"R$ {total_recebido:,.2f}")
                kpi3.metric("Pendência do Mês", f"R$ {total_previsto - total_recebido:,.2f}")

                # Exibição
                st.subheader("📋 Lista de Conciliação")
                st.dataframe(conciliacao[['Contrato', 'Data_Vencto', 'Valor_Previsto', 'Status', 'Valor_Pago']], use_container_width=True)

        except Exception as e:
            st.error(f"Erro ao processar: {e}")
    else:
        st.info("Aguardando upload dos arquivos.")
