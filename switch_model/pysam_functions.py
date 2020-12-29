# Import the PySAM modules for simulating solar, CSP, and wind power generation
import PySAM.ResourceTools as tools
import PySAM.Pvwattsv7 as pv
import PySAM.TcsmoltenSalt as csp_tower
import PySAM.Windpower as wind

def simulate_solar_generation(nrel_api_key, nrel_api_email, resource_dict, config_dict, resource_years, input_dir, tz_offset):
    
    #initiate the default PV setup
    system_model_PV = pv.default('PVWattsSingleOwner')

    # specify non-default system design factors
    systemDesign = config_dict['SystemDesign']

    #assign the non-default system design specs to the model
    system_model_PV.SystemDesign.assign(systemDesign)

    lon_lats = list(resource_dict.keys())

    #this is the df that will hold all of the data for all years
    df_resource = pd.DataFrame(data=range(1,8761), columns=['timepoint']).set_index('timepoint')
    df_index = df_resource.index

    for year in resource_years:

        #download resource files
        #https://github.com/NREL/pysam/blob/master/Examples/FetchResourceFileExample.py
        #https://nrel-pysam.readthedocs.io/en/master/Tools.html?highlight=download#files.ResourceTools.FetchResourceFiles

        #TODO: allow to fetch single resource year
        nsrdbfetcher = tools.FetchResourceFiles(
                        tech='solar',
                        workers=1,  # thread workers if fetching multiple files
                        nrel_api_key=nrel_api_key,
                        resource_type='psm3',
                        resource_year=str(year),
                        nrel_api_email=nrel_api_email,
                        resource_dir=(input_dir / 'PySAM Downloaded Weather Files/PV'))

        #fetch resource data from the dictionary
        nsrdbfetcher.fetch(lon_lats)

        #get a dictionary of all of the filepaths
        nsrdb_path_dict = nsrdbfetcher.resource_file_paths_dict

        for filename in nsrdb_path_dict:
            solarResource = tools.SAM_CSV_to_solar_data(nsrdb_path_dict[filename])
            
            #assign the solar resource input file to the model
            system_model_PV.SolarResource.solar_resource_data = solarResource

            #execute the system model
            system_model_PV.execute()

            #access sytem power generated output
            output = system_model_PV.Outputs.gen
            df_output = pd.DataFrame(output)

            #roll the data to get into pacific time
            roll = int(tz_offset  - system_model_PV.Outputs.tz)
            df_output = pd.DataFrame(np.roll(df_output, roll))

            #calculate capacity factor
            df_output = df_output / systemDesign['system_capacity']

            #name the column based on resource name
            df_output = df_output.rename(columns={0:f'{resource_dict[filename]}-{year}'})

            #merge into the resource
            df_output.index = df_index
            df_resource = df_resource.merge(df_output, how='left', left_index=True, right_index=True)

    #remove year from column name
    df_resource.columns = [i.split('-')[0] for i in df_resource.columns]

    #groupby column name
    df_resource = df_resource.groupby(df_resource.columns, axis=1).mean()

    return df_resource

def simulate_wind_generation(nrel_api_key, nrel_api_email, resource_dict, config_dict, resource_years, input_dir, tz_offset):
    
    #initiate the default wind power setup
    system_model_wind = wind.default('WindPowerSingleOwner')

    # specify non-default system design factors
    turbine = config_dict['Turbine']
    farm = config_dict['Farm']
    resource = config_dict['Resource']

    #assign the non-default system design specs to the model
    system_model_wind.Turbine.assign(turbine)
    system_model_wind.Farm.assign(farm)

    lon_lats = list(resource_dict.keys())

    #this is the df that will hold all of the data for all years
    df_resource = pd.DataFrame(data=range(1,8761), columns=['timepoint']).set_index('timepoint')
    df_index = df_resource.index

    for year in resource_years:

        #specify wind data input
        wtkfetcher = tools.FetchResourceFiles(
                        tech='wind',
                        workers=1,  # thread workers if fetching multiple files
                        nrel_api_key=nrel_api_key,
                        nrel_api_email=nrel_api_email,
                        resource_year=str(year),
                        resource_height=resource['resource_height'],
                        resource_dir=(input_dir / 'PySAM Downloaded Weather Files/Wind'))

        #fetch resource data from the dictionary
        wtkfetcher.fetch(lon_lats)

        #get a dictionary of all of the filepaths
        wtk_path_dict = wtkfetcher.resource_file_paths_dict

        for filename in wtk_path_dict:

            windResource = tools.SRW_to_wind_data(wtk_path_dict[filename])
            
            #assign the wind resource input data to the model
            system_model_wind.Resource.wind_resource_data = windResource

            #execute the system model
            system_model_wind.execute()

            #access sytem power generated output
            output = system_model_wind.Outputs.gen

            df_output = pd.DataFrame(output)

            #calculate capacity factor
            df_output = df_output / farm['system_capacity']

            #name the column based on resource name
            df_output = df_output.rename(columns={0:f'{resource_dict[filename]}-{year}'})

            #merge into the resource
            df_output.index = df_index
            df_resource = df_resource.merge(df_output, how='left', left_index=True, right_index=True)

    #remove year from column name
    df_resource.columns = [i.split('-')[0] for i in df_resource.columns]

    #groupby column name
    df_resource = df_resource.groupby(df_resource.columns, axis=1).mean()

    return df_resource

def simulate_csp_generation(nrel_api_key, nrel_api_email, resource_dict, config_dict, resource_years, input_dir, tz_offset):
    
    #initiate the default PV setup
    system_model_MSPT = csp_tower.default('MSPTSingleOwner')

    # specify non-default system design factors
    systemDesign = config_dict['SystemDesign']
    timeOfDeliveryFactors = config_dict['TimeOfDeliveryFactors']
    systemControl = config_dict['SystemControl']

    #assign the non-default system design specs to the model
    system_model_MSPT.SystemControl.assign(systemControl)
    system_model_MSPT.TimeOfDeliveryFactors.assign(timeOfDeliveryFactors)
    system_model_MSPT.SystemDesign.assign(systemDesign)

    lon_lats = list(resource_dict.keys())

    #this is the df that will hold all of the data for all years
    df_resource = pd.DataFrame(data=range(1,8761), columns=['timepoint']).set_index('timepoint')
    df_index = df_resource.index

    for year in resource_years:

        #download resource files
        #https://github.com/NREL/pysam/blob/master/Examples/FetchResourceFileExample.py
        #https://nrel-pysam.readthedocs.io/en/master/Tools.html?highlight=download#files.ResourceTools.FetchResourceFiles

        nsrdbfetcher = tools.FetchResourceFiles(
                        tech='solar',
                        workers=1,  # thread workers if fetching multiple files
                        nrel_api_key=nrel_api_key,
                        resource_type='psm3',
                        resource_year=str(year),
                        nrel_api_email=nrel_api_email,
                        resource_dir=(input_dir / 'PySAM Downloaded Weather Files/CSP'))

        #fetch resource data from the dictionary
        nsrdbfetcher.fetch(lon_lats)

        #get a dictionary of all of the filepaths
        nsrdb_path_dict = nsrdbfetcher.resource_file_paths_dict

        for filename in nsrdb_path_dict:
            #convert TMY data to be used in SAM
            #solarResource = tools.SAM_CSV_to_solar_data(nsrdb_path_dict[filename])

            #assign the solar resource input file to the model
            #system_model_MSPT.SolarResource.solar_resource_data = solarResource
            system_model_MSPT.SolarResource.solar_resource_file = nsrdb_path_dict[filename]
            
            #execute the system model
            system_model_MSPT.execute()

            #access sytem power generated output
            output = system_model_MSPT.Outputs.gen

            #roll the data to get into pacific time
            df_output = pd.DataFrame(output)

            #calculate capacity factor
            df_output = df_output / (systemDesign['P_ref'] * 1000)

            #name the column based on resource name
            df_output = df_output.rename(columns={0:f'{resource_dict[filename]}-{year}'})

            #merge into the resource
            df_output.index = df_index
            df_resource = df_resource.merge(df_output, how='left', left_index=True, right_index=True)

    #remove year from column name
    df_resource.columns = [i.split('-')[0] for i in df_resource.columns]

    #groupby column name
    df_resource = df_resource.groupby(df_resource.columns, axis=1).mean()

    return df_resource