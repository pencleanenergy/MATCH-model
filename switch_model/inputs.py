"""
This takes data from an input excel file and formats into individual csv files for inputs
TODO:
- [ ] Copy summary_report into input directory
- [ ] Generate the following input csv files:


"""
#%%
import pandas as pd 
from pathlib import Path

model_inputs = Path.cwd() / '../time_coincident/model_inputs.xlsx'

input_dir = Path.cwd() / '../time_coincident/inputs/'

#%%
#read excel, for now use input year
xl_general = pd.read_excel(io=model_inputs, sheet_name='general')


#%%
year = int(xl_general.loc[xl_general['Parameter'] == 'Model Year', 'Input'].item())

# periods.csv
df_periods = pd.DataFrame(columns=['INVESTMENT_PERIOD','period_start','period_end'], data=[[year,year,year]])
#df_periods.to_csv(input_dir / 'periods.csv', index=False)

# timeseries.csv
df_timeseries = pd.DataFrame(
    data={'TIMESERIES': [f'{year}_timeseries'],
          'ts_period': [year],
          'ts_duration_of_tp': [1], #duration (hour) of each timepoint
          'ts_num_tps': [8760], #number of timepoints in the timeseries
          'ts_scale_to_period': [1]} #number of timeseries in period
          )
#df_timeseries.to_csv(input_dir / 'timeseries.csv', index=False)

#%%
# timepoints.csv
df_timepoints = pd.DataFrame(index=pd.date_range(start=f'01/01/{year} 00:00', end=f'12/31/{year} 23:00', freq='1H'))
df_timepoints['timeseries'] = f'{year}_timeseries'
df_timepoints['timestamp'] = df_timepoints.index.strftime('%m/%d/%Y %H:%M')
df_timepoints['tp_month'] = df_timepoints.index.month
df_timepoints['tp_day'] = df_timepoints.index.dayofyear
df_timepoints = df_timepoints.reset_index(drop=True)
df_timepoints['timepoint_id'] = df_timepoints.index + 1
#df_timepoints[['timepoint_id','timestamp','timeseries']].to_csv(input_dir / 'timepoints.csv', index=False)

# months.csv
#df_timepoints[['timepoint_id','tp_month']].to_csv(input_dir / 'months.csv', index=False)

# days.csv
#df_timepoints[['timepoint_id','tp_day']].to_csv(input_dir / 'days.csv', index=False)

#%%
#financials
df_financials = pd.DataFrame(
    data={'base_financial_year': [int(xl_general.loc[xl_general['Parameter'] == 'Base Financial Year', 'Input'].item())],
          'discount_rate': [xl_general.loc[xl_general['Parameter'] == 'Discount Rate', 'Input'].item()],
          'interest_rate': [xl_general.loc[xl_general['Parameter'] == 'Interest Rate', 'Input'].item()]}
)
#df_financials.to_csv(input_dir / 'financials.csv', index=False)

# %%
xl_load = pd.read_excel(io=model_inputs, sheet_name='load', skiprows=2, index_col='Datetime')

load_list = list(xl_load.columns)

df_load_zones = pd.DataFrame(data={'LOAD_ZONE':load_list})
#df_load_zones.to_csv(input_dir / 'load_zones.csv', index=False)

df_loads = pd.DataFrame(columns=['LOAD_ZONE','TIMEPOINT','zone_demand_mw'])

# %%
