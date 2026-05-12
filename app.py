import streamlit as st
import pandas as pd
import pdfplumber
import re
from io import BytesIO
from fpdf import FPDF

# Configuração da página
st.set_page_config(page_title="Conciliador PAX Pro", layout="wide")

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
    """Extração robusta de dados dos PDFs."""
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
                            # Captura tudo para o "Total Bruto", mas identifica competência para conciliar
                            data.append({'Contrato': contrato, 'Mes_Ref': data_dt.month, 'Ano_Ref': data_dt.year, 'Valor_Pago': valor})
    return pd.DataFrame(data)

def generate_pdf(df, stats, mes, ano):
    """Gera o relatório em PDF."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(190, 10, f"Relatorio de Conciliacao PAX - {mes}/{ano}", ln=True, align='C')
    
    pdf.set_font("Arial", '', 11)
    pdf.ln(10)
    pdf.cell(100, 8, f"Total Identificado nos Arquivos (Bruto): R$ {stats['bruto']:,.2f}")
    pdf.ln(7)
    pdf.cell(100, 8, f"Total Previsto para o Mes: R$ {stats['previsto']:,.2f}")
    pdf.ln(7)
    pdf.cell(100, 8, f"Total Conciliado (Pago do Mes): R$ {stats['pago']:,.2f}")
    pdf.ln(7)
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(100, 8, f"Valor Inadimplente: R$ {stats['pendente']:,.2f}")
    pdf.ln(7)
    pdf.set_text_color(200, 0, 0)
    pdf.cell(100, 8, f"Percentual de Inadimplencia: {stats['perc']:.2f}%")
    pdf.set_text_color(0, 0, 0)
    
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 9)
    pdf.cell(30, 7, "Contrato", 1)
    pdf.cell(35, 7, "Vencimento", 1)
    pdf.cell(35, 7, "Previsto", 1)
    pdf.cell(35, 7, "Pago", 1)
    pdf.cell(50, 7, "Status", 1)
    pdf.ln()
    
    pdf.set_font("Arial", '', 8)
    for i, r in df.head(150).iterrows():
        pdf.cell(30, 6, str(r['Contrato']), 1)
        pdf.cell(35, 6, r['Data_Vencto'].strftime('%d/%m/%Y'), 1)
        pdf.cell(35, 6, f"{r['Valor_Previsto']:,.2f}", 1)
        pdf.cell(35, 6, f"{r['Valor_Pago']:,.2f}", 1)
        pdf.cell(50, 6, "PAGO" if r['Valor_Pago'] > 0 else "PENDENTE", 1)
        pdf.ln()
    return pdf.output(dest='S').encode('latin-1')

st.title("📊 Gestão Financeira - Conciliação & Inadimplência")

col1, col2 = st.columns(2)
with col1:
    files_receber = st.file_uploader("Arquivos A RECEBER (PDF)", accept_multiple_files=True)
with col2:
    files_recebidos = st.file_uploader("Arquivos RECEBIDOS (PDF)", accept_multiple_files=True)

st.sidebar.header("Parâmetros do Mês")
mes = st.sidebar.selectbox("Mês de Vencimento", range(1, 13), index=4)
ano = st.sidebar.number_input("Ano", value=2026)

if st.button("🚀 Iniciar Conciliação"):
    if files_receber and files_recebidos:
        with st.spinner("Processando..."):
            df_receber = process_file(files_receber, mode="receber")
            df_recebidos = process_file(files_recebidos, mode="recebidos")
            
            # --- CALCULOS ---
            # 1. Total Bruto (Soma de tudo que foi lido nos arquivos de recebimento, sem filtro)
            total_bruto_identificado = df_recebidos['Valor_Pago'].sum()
            
            # 2. Filtro de competência (Vencimento do mês selecionado)
            df_receber_mes = df_receber[(df_receber['Data_Vencto'].dt.month == mes) & (df_receber['Data_Vencto'].dt.year == ano)]
            
            # 3. Filtro de recebidos que pertencem a esse vencimento
            df_rec_total = df_recebidos[(df_recebidos['Mes_Ref'] == mes) & (df_recebidos['Ano_Ref'] == ano)].groupby('Contrato')['Valor_Pago'].sum().reset_index()
            
            # 4. Merge final
            conciliacao = pd.merge(df_receber_mes, df_rec_total, on='Contrato', how='left').fillna(0)
            
            total_previsto = conciliacao['Valor_Previsto'].sum()
            total_pago_mes = conciliacao['Valor_Pago'].sum()
            total_pendente = total_previsto - total_pago_mes
            perc_inadimplencia = (total_pendente / total_previsto * 100) if total_previsto > 0 else 0
            
            stats = {
                'bruto': total_bruto_identificado,
                'previsto': total_previsto,
                'pago': total_pago_mes,
                'pendente': total_pendente,
                'perc': perc_inadimplencia
            }

            # --- DISPLAY ---
            st.divider()
            # Primeira linha de cards: Recebimentos e Conciliação
            kpi1, kpi2, kpi3 = st.columns(3)
            kpi1.metric("Total Identificado (Arquivos)", f"R$ {total_bruto_identificado:,.2f}")
            kpi2.metric("A Receber (Esperado no Mês)", f"R$ {total_previsto:,.2f}")
            kpi3.metric("Conciliado (Pago do Mês)", f"R$ {total_pago_mes:,.2f}")
            
            # Segunda linha de cards: Inadimplência
            st.markdown("### 🔴 Indicadores de Inadimplência")
            k1, k2 = st.columns(2)
            k1.metric("Valor Inadimplente", f"R$ {total_pendente:,.2f}")
            k2.metric("% Inadimplência", f"{perc_inadimplencia:.2f}%", delta_color="inverse")

            st.subheader("📋 Tabela de Detalhes")
            st.dataframe(conciliacao, use_container_width=True)

            # --- EXPORTAÇÃO ---
            st.divider()
            exp1, exp2 = st.columns(2)
            with exp1:
                output_xlsx = BytesIO()
                with pd.ExcelWriter(output_xlsx, engine='openpyxl') as writer:
                    conciliacao.to_excel(writer, index=False, sheet_name='Detalhamento')
                st.download_button("📥 Baixar Excel", output_xlsx.getvalue(), f"detalhe_pax_{mes}_{ano}.xlsx")
            
            with exp2:
                try:
                    pdf_bytes = generate_pdf(conciliacao, stats, mes, ano)
                    st.download_button("📥 Baixar Relatório PDF", pdf_bytes, f"relatorio_pax_{mes}_{ano}.pdf")
                except Exception as e:
                    st.error(f"Erro ao gerar PDF: {e}")
    else:
        st.warning("Envie os arquivos PDF para continuar.")
