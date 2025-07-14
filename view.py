import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from datetime import datetime
from category import MerchantMap, CategoryConfig
import re


# 加载配置
merchant_map = MerchantMap('merchant_map.json')
category_cfg = CategoryConfig('category.json')


def match_category(df: pd.DataFrame, category_patterns: dict):
    df_copy = df.copy()
    df_copy['Category'] = 'Other'
    for cat, patterns in category_patterns.items():
        regex = re.compile('|'.join(patterns), re.IGNORECASE)
        mask = df_copy['Merchant'].astype(str).str.contains(regex)
        df_copy.loc[mask, 'Category'] = cat
    return df_copy

def display_overall_summary(filtered_df: pd.DataFrame):
    if filtered_df.empty:
        st.info('No data in this period')
    else:
        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Total Refund", f"${-filtered_df[filtered_df['Amount'] < 0]['Amount'].sum():.2f}")
        col_b.metric("Total Outcome", f"${filtered_df[filtered_df['Amount'] >= 0]['Amount'].sum():.2f}")
        col_c.metric("Net Spend", f"${filtered_df['Amount'].sum():.2f}")
        
        df_list_matched = match_category(filtered_df, category_cfg.categories)
        sums = df_list_matched.groupby('Category')['Amount'].sum()
        percentages = sums / sums.sum()
        label_with_percentages = [f"{label} ({percentage:.1%})" for label, percentage in zip(sums.index, percentages)]
        fig, ax = plt.subplots(figsize=(5, 5))  
        ax.pie(sums, labels=label_with_percentages, startangle=90, textprops={'fontsize': 16})
        ax.axis('equal')
        st.pyplot(fig)
        
def favorite_stores(filtered_df):
    if filtered_df.empty:
        st.info('No data in this period')
    else:
        df_grouped = filtered_df.groupby('Merchant')['Amount'].sum()
        df_grouped = df_grouped.sort_values(ascending=False)
        st.dataframe(df_grouped)

def plot_linear_spending(spend_date_list, spend_list):
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(spend_date_list, spend_list, marker='o')
    ax.axhline(0, color='gray', linestyle='--')
    ax.set_title("Net Spending")
    ax.set_xlabel("Date")
    ax.set_ylabel("Amount ($)")
    ax.grid(True)
    plt.xticks(rotation=45)
    st.pyplot(fig)

def plot_net_spend(df_list_in_unit):
    """
    合并df_list，使用正则对Category进行模糊匹配归类，输出每个Category的净支出表格。
    :param df_list: List[pd.DataFrame]，每个df需有'Merchant'和'Amount'列
    :param category_patterns: dict, {category: [pattern1, pattern2, ...]}
    :return: pd.DataFrame, columns=['Category', 'Net Spend']
    """

    category_patterns = category_cfg.categories
    matrix = []
    row_labels = []
    for df in df_list_in_unit:
        df_list_matched = match_category(df, category_patterns)
        sums = df_list_matched.groupby('Category')['Amount'].sum()
        matrix.append(sums)
        row_labels.append(df['Date'].iloc[0].date())
    result = pd.DataFrame(matrix).fillna(0)
    result.index = row_labels
    st.dataframe(result)




# Main
if __name__ == "__main__":
    import pandas as pd

    # Load the uploaded CSV file into a DataFrame
    df = pd.read_csv("test_excel.csv")
