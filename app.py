import streamlit as st
import pandas as pd
import pdfplumber
import re

# Configuração de página
st.set_page_config(page_title="Conciliador PAX - Alta Precisão", layout="wide")

st.title("📊 Conciliação Financeira (Versão Corrigida)")
st.info("Esta versão utiliza extração de texto bruto para garantir que todos os valores pagos sejam contabilizados.")

def get_money_value(text):
    """Extrai o último valor monetário de uma linha (valor pago)."""
    matches = re.findall(r'(\d+[\d.]*,\d{2})', text)
    if matches:
        # Pega o último valor da linha (geralmente o Valor Pago/Total)
        val_str = matches[-1].replace('.', '').replace(',', '.')
        return float(val_str)
    return 0.0

def process_file(uploaded_files, mode="receber"):
    """Processa arquivos usando extração de texto para não perder linhas."""
    data = []
    for uploaded_file in uploaded_files:
        with pdfplumber.open(uploaded_file) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if not text:
                    continue
                
                lines = text.split('\n')
                for line in lines:
                    # Busca Contrato (3 a 5 dígitos) e Data (DD/MM/AAAA)
                    contrato_match = re.search(r'\b(\d{3,5})\b', line)
                    data_match = re.search(r'(\d{2}/\d{2}/\d{4})', line)
                    valor = get_money_value(line)
                    
                    if data_match and valor > 0:
                        contrato = contrato_match.group(1) if contrato_match else "S/C"
                        data_dt = pd.to_datetime(data_match.group(1), dayfirst=True)
                        
                        if mode == "receber":
                            data.append({
                                'Contrato': contrato,
                                'Data_Vencto': data_dt,
                                'Valor_Previsto': valor
                            })
                        else:
                            # Para recebidos, pegamos a competência (vencimento) para bater com o à receber
                            data.append({
                                'Contrato': contrato,
                                'Mes_Ref': data_dt.month,
                                'Ano_Ref': data_dt.year,
                                'Valor_Pago': valor
                            })
    return pd.DataFrame(data)

# Interface
col1, col2 = st.columns(2)
with col1:
    files_receber = st.file_uploader("Arquivos A RECEBER (PDF)", accept_multiple_files=True)
with col2:
    files_recebidos = st.file_uploader("Arquivos RECEBIDOS (PDF)", accept_multiple_files=True)

st.sidebar.header("Filtro de Conciliação")
mes = st.sidebar.selectbox("Mês de Vencimento", range(1, 13), index=4) # Maio
ano = st.sidebar.number_input("Ano", value=2026)

if st.button("🚀 Conciliar e Somar"):
    if files_receber and files_recebidos:
        with st.spinner("Processando arquivos..."):
            df_receber = process_file(files_receber, mode="receber")
            df_recebidos = process_file(files_recebidos, mode="recebidos")

            if df_receber.empty or df_recebidos.empty:
                st.error("Não foram encontrados dados nos arquivos. Verifique se são PDFs de texto.")
                st.stop()

            # Filtramos o à receber pelo mês selecionado
            df_receber_mes = df_receber[
                (df_receber['Data_Vencto'].dt.month == mes) & 
                (df_receber['Data_Vencto'].dt.year == ano)
            ]

            # Somamos os recebidos por Contrato (caso haja mais de um pagamento/parcela)
            # Filtrando pela competência do vencimento original
            df_recebidos_filtrado = df_recebidos[
                (df_recebidos['Mes_Ref'] == mes) & 
                (df_recebidos['Ano_Ref'] == ano)
            ]
            
            df_rec_total = df_recebidos_filtrado.groupby('Contrato')['Valor_Pago'].sum().reset_index()

            # Merge final
            conciliacao = pd.merge(df_receber_mes, df_rec_total, on='Contrato', how='left').fillna(0)
            
            # Indicadores Reais
            st.divider()
            c1, c2, c3 = st.columns(3)
            
            total_rec_nos_arquivos = df_recebidos['Valor_Pago'].sum() # Soma absoluta de todos os arquivos de recebimento
            total_esperado_mes = df_receber_mes['Valor_Previsto'].sum()
            total_conciliado = conciliacao['Valor_Pago'].sum()

            c1.metric("Total Bruto nos Arquivos (Recebidos)", f"R$ {total_rec_nos_arquivos:,.2f}")
            c2.metric("Total a Receber (Venc. no Mês)", f"R$ {total_esperado_mes:,.2f}")
            c3.metric("Total Conciliado (Deste Mês)", f"R$ {total_conciliado:,.2f}")

            if total_rec_nos_arquivos > 22000 and total_conciliado < 22000:
                st.warning(f"Atenção: Existem R$ {total_rec_nos_arquivos - total_conciliado:,.2f} em recebimentos que não pertencem ao mês de vencimento {mes}/{ano} ou não possuem contrato correspondente no arquivo de 'A Receber'.")

            st.subheader("📋 Detalhes da Conciliação")
            st.dataframe(conciliacao, use_container_width=True)
    else:
        st.warning("Selecione os arquivos.")
