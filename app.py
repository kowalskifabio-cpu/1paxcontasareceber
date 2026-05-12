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
    """Extrai dados dos PDFs e retorna um DataFrame único."""
    all_data = []
    
    for uploaded_file in uploaded_files:
        with pdfplumber.open(uploaded_file) as pdf:
            for page in pdf.pages:
                table = page.extract_table()
                if table:
                    # O primeiro item costuma ser o cabeçalho, os demais são dados
                    for row in table[1:]:
                        # Limpeza básica de ruídos comuns em extração de PDF
                        clean_row = [str(item).replace('\n', ' ').strip() if item else "" for item in row]
                        all_data.append(clean_row)
    
    # Criando DataFrame inicial (ajustar nomes de colunas conforme estrutura detectada)
    df = pd.DataFrame(all_data)
    return df

def preprocess_receber(df):
    """Tratamento específico para arquivos 'A Receber'."""
    # Baseado na estrutura: Controle, Contrato, Cliente, Dt.Vencto, Valor...
    # Como a extração de PDF pode variar, buscamos padrões de Contrato e Data
    new_rows = []
    for _, row in df.iterrows():
        row_str = " ".join(row.values)
        # Regex para capturar Contrato (4 dígitos), Data (DD/MM/AAAA) e Valor (R$)
        contrato = re.search(r'(\d{4})', row_str)
        data = re.search(r'(\d{2}/\d{2}/\d{4})', row_str)
        valor = re.search(r'(\d+,\d{2})', row_str)
        
        if contrato and data and valor:
            new_rows.append({
                'Contrato': contrato.group(1),
                'Data_Vencto': pd.to_datetime(data.group(1), dayfirst=True),
                'Valor_Previsto': float(valor.group(1).replace('.', '').replace(',', '.')),
                'Cliente': row[2] if len(row) > 2 else "N/D"
            })
    return pd.DataFrame(new_rows)

def preprocess_recebidos(df):
    """Tratamento específico para arquivos 'Recebidos'."""
    new_rows = []
    for _, row in df.iterrows():
        row_str = " ".join(row.values)
        contrato = re.search(r'(\d{4})', row_str)
        data_venc = re.search(r'(\d{2}/\d{2}/\d{4})', row_str) # Pega o primeiro (vencimento)
        valor = re.search(r'(\d+,\d{2})', row_str)
        
        if contrato and data_venc and valor:
            new_rows.append({
                'Contrato': contrato.group(1),
                'Mês_Referência': pd.to_datetime(data_venc.group(1), dayfirst=True).month,
                'Ano_Referência': pd.to_datetime(data_venc.group(1), dayfirst=True).year,
                'Valor_Pago': float(valor.group(1).replace('.', '').replace(',', '.')),
                'Status': 'Recebido'
            })
    return pd.DataFrame(new_rows)

# Interface de Upload
col1, col2 = st.columns(2)

with col1:
    st.subheader("📁 Arquivos 'A Receber'")
    files_receber = st.file_uploader("Upload (A RECEBER / EM ATRASO)", type="pdf", accept_multiple_files=True)

with col2:
    st.subheader("📁 Arquivos 'Recebidos'")
    files_recebidos = st.file_uploader("Upload (RECEBIDAS / EM ATRASO)", type="pdf", accept_multiple_files=True)

# Filtros de Mês/Ano
st.sidebar.header("Configurações de Conciliação")
mes_selecionado = st.sidebar.selectbox("Selecione o Mês", range(1, 13), index=4) # Default Maio
ano_selecionado = st.sidebar.number_input("Selecione o Ano", min_value=2024, max_value=2030, value=2026)

if st.button("🚀 Processar e Conciliar"):
    if files_receber and files_recebidos:
        try:
            # 1. Extração e Processamento
            with st.spinner("Extraindo dados dos PDFs..."):
                df_receber_raw = extract_data_from_pdf(files_receber)
                df_recebidos_raw = extract_data_from_pdf(files_recebidos)
                
                df_receber = preprocess_receber(df_receber_raw)
                df_recebidos = preprocess_recebidos(df_recebidos_raw)
            
            # 2. Filtragem pelo Mês de Referência
            df_receber_mes = df_receber[(df_receber['Data_Vencto'].dt.month == mes_selecionado) & 
                                        (df_receber['Data_Vencto'].dt.year == ano_selecionado)]
            
            # 3. Conciliação (Merge)
            conciliacao = pd.merge(
                df_receber_mes, 
                df_recebidos, 
                on='Contrato', 
                how='left'
            )
            
            conciliacao['Status'] = conciliacao['Status'].fillna('Pendente')
            
            # 4. Indicadores
            st.divider()
            st.header("📈 Indicadores do Mês")
            
            kpi1, kpi2, kpi3 = st.columns(3)
            total_previsto = conciliacao['Valor_Previsto'].sum()
            total_recebido = conciliacao[conciliacao['Status'] == 'Recebido']['Valor_Previsto'].sum()
            inadimplencia = total_previsto - total_recebido
            
            kpi1.metric("Total a Receber", f"R$ {total_previsto:,.2f}")
            kpi2.metric("Total Conciliado (Pago)", f"R$ {total_recebido:,.2f}", delta=f"{(total_recebido/total_previsto)*100:.1f}%")
            kpi3.metric("Pendente (Inadimplência)", f"R$ {inadimplencia:,.2f}", delta_color="inverse")
            
            # 5. Visualização de Dados
            st.subheader("Detalhamento da Conciliação")
            st.dataframe(conciliacao.style.applymap(
                lambda x: 'background-color: #d4edda' if x == 'Recebido' else 'background-color: #f8d7da',
                subset=['Status']
            ), use_container_width=True)
            
            # 6. Exportação
            csv = conciliacao.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 Baixar Relatório Conciliado (CSV)", csv, "conciliacao_pax.csv", "text/csv")
            
        except Exception as e:
            st.error(f"Erro ao processar: {e}")
    else:
        st.warning("Por favor, envie os arquivos de ambos os lados para conciliar.")
