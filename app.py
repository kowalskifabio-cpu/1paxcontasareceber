import streamlit as st
import pandas as pd
import pdfplumber
import re
from io import BytesIO
from fpdf import FPDF

# Configuração da página
st.set_page_config(page_title="Conciliador Financeiro Pro", layout="wide")

def get_money_value(text):
    """Extrai o último valor monetário de uma linha."""
    if not text: return 0.0
    matches = re.findall(r'(\d+[\d.]*,\d{2})', text)
    if matches:
        val_str = matches[-1].replace('.', '').replace(',', '.')
        try: return float(val_str)
        except: return 0.0
    return 0.0

def process_file(uploaded_files, mode="receber"):
    """Extração de dados dos PDFs."""
    data = []
    for uploaded_file in uploaded_files:
        with pdfplumber.open(uploaded_file) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if not text: continue
                lines = text.split('\n')
                for line in lines:
                    contrato_match = re.search(r'\b(\d{3,5})\b', line)
                    data_match = re.search(r'(\d{2}/\d{2}/\d{4})', line)
                    valor = get_money_value(line)
                    
                    if data_match and valor > 0:
                        contrato = contrato_match.group(1) if contrato_match else "S/C"
                        data_dt = pd.to_datetime(data_match.group(1), dayfirst=True)
                        if mode == "receber":
                            data.append({'Contrato': contrato, 'Data_Vencto': data_dt, 'Valor_Previsto': valor})
                        else:
                            data.append({'Contrato': contrato, 'Mes_Ref': data_dt.month, 'Ano_Ref': data_dt.year, 'Valor_Pago': valor})
    return pd.DataFrame(data)

def generate_pdf(df, stats, mes, ano):
    """Gera um PDF simples com o resumo e a tabela."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(190, 10, f"Relatorio de Conciliacao - {mes}/{ano}", ln=True, align='C')
    
    pdf.set_font("Arial", '', 12)
    pdf.ln(10)
    pdf.cell(100, 10, f"Total Previsto: R$ {stats['previsto']:,.2f}")
    pdf.ln(7)
    pdf.cell(100, 10, f"Total Conciliado: R$ {stats['pago']:,.2f}")
    pdf.ln(7)
    pdf.cell(100, 10, f"Inadimplencia: R$ {stats['pendente']:,.2f}")
    pdf.ln(7)
    pdf.set_text_color(255, 0, 0)
    pdf.cell(100, 10, f"Percentual de Inadimplencia: {stats['perc']:.2f}%")
    pdf.set_text_color(0, 0, 0)
    
    pdf.ln(15)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(30, 8, "Contrato", 1)
    pdf.cell(40, 8, "Vencimento", 1)
    pdf.cell(40, 8, "Previsto", 1)
    pdf.cell(40, 8, "Pago", 1)
    pdf.cell(40, 8, "Status", 1)
    pdf.ln()
    
    pdf.set_font("Arial", '', 9)
    for i, r in df.head(100).iterrows(): # Limite de 100 linhas no PDF para não travar
        pdf.cell(30, 7, str(r['Contrato']), 1)
        pdf.cell(40, 7, r['Data_Vencto'].strftime('%d/%m/%Y'), 1)
        pdf.cell(40, 7, f"{r['Valor_Previsto']:.2f}", 1)
        pdf.cell(40, 7, f"{r['Valor_Pago']:.2f}", 1)
        pdf.cell(40, 7, "Pago" if r['Valor_Pago'] > 0 else "Pendente", 1)
        pdf.ln()
    
    return pdf.output(dest='S').encode('latin-1')

st.title("📊 Conciliador Financeiro Pro")

col1, col2 = st.columns(2)
with col1:
    files_receber = st.file_uploader("Arquivos A RECEBER (PDF)", accept_multiple_files=True)
with col2:
    files_recebidos = st.file_uploader("Arquivos RECEBIDOS (PDF)", accept_multiple_files=True)

st.sidebar.header("Filtros")
mes = st.sidebar.selectbox("Mês", range(1, 13), index=4)
ano = st.sidebar.number_input("Ano", value=2026)

if st.button("🚀 Processar Conciliação"):
    if files_receber and files_recebidos:
        df_receber = process_file(files_receber, mode="receber")
        df_recebidos = process_file(files_recebidos, mode="recebidos")
        
        # Filtro de competência
        df_receber_mes = df_receber[(df_receber['Data_Vencto'].dt.month == mes) & (df_receber['Data_Vencto'].dt.year == ano)]
        df_rec_total = df_recebidos[(df_recebidos['Mes_Ref'] == mes) & (df_recebidos['Ano_Ref'] == ano)].groupby('Contrato')['Valor_Pago'].sum().reset_index()
        
        conciliacao = pd.merge(df_receber_mes, df_rec_total, on='Contrato', how='left').fillna(0)
        
        # Cálculos de Indicadores
        total_previsto = conciliacao['Valor_Previsto'].sum()
        total_pago = conciliacao['Valor_Pago'].sum()
        total_pendente = total_previsto - total_pago
        perc_inadimplencia = (total_pendente / total_previsto * 100) if total_previsto > 0 else 0
        
        stats = {'previsto': total_previsto, 'pago': total_pago, 'pendente': total_pendente, 'perc': perc_inadimplencia}

        # Cards de Indicadores
        st.divider()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Previsto no Mês", f"R$ {total_previsto:,.2f}")
        c2.metric("Total Conciliado", f"R$ {total_pago:,.2f}")
        c3.metric("Inadimplência (R$)", f"R$ {total_pendente:,.2f}")
        c4.metric("% Inadimplência", f"{perc_inadimplencia:.2f}%", delta_color="inverse")

        st.subheader("📋 Detalhamento da Conciliação")
        st.dataframe(conciliacao, use_container_width=True)

        # Botões de Exportação
        st.divider()
        exp1, exp2 = st.columns(2)
        
        with exp1:
            # Exportar Excel
            output_xlsx = BytesIO()
            with pd.ExcelWriter(output_xlsx, engine='openpyxl') as writer:
                conciliacao.to_excel(writer, index=False, sheet_name='Conciliacao')
            st.download_button("📥 Baixar Detalhamento (Excel)", output_xlsx.getvalue(), f"conciliacao_{mes}_{ano}.xlsx")
            
        with exp2:
            # Exportar PDF
            try:
                pdf_bytes = generate_pdf(conciliacao, stats, mes, ano)
                st.download_button("📥 Baixar Relatório (PDF)", pdf_bytes, f"relatorio_{mes}_{ano}.pdf")
            except:
                st.error("Erro ao gerar PDF (verifique caracteres especiais nos nomes dos clientes).")

    else:
        st.warning("Envie os arquivos para processar.")
