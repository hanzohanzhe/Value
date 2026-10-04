# Model framework

VALUE links electricity-system operation to annual changes in the asset fleet. In each model year, available generation, storage and transmission capacity determine the supply–demand balance. Operating revenues, costs and expansion limits then enter the investment rules that form the following year's fleet. The principal outputs are generation and storage operation, unserved energy, system resource cost, carbon emissions, and capacity additions and retirements.

## Temporal and spatial representation

VALUE uses a 0.5-hour operating interval and 17,520 intervals per model year. Power is measured in MW and interval energy in MWh, with energy equal to power multiplied by the interval duration. Investment is updated after a complete operating year, and the sequence of annual updates determines fleet development over the study period.

The national model represents Great Britain's electricity system as a single supply–demand node, with external electricity exchange represented by boundary offers. The zonal model additionally specifies the locations of resources and demand and the capacities of corridors between nodes. The two zonal research configurations use 23 zones and 22 corridors, and 11 zones and 14 computational corridors, respectively. Each configuration uses its associated demand allocation, asset mapping and boundary capacities.

## Annual calculation

The initial fleet, construction pipeline, demand and weather determine annual operation. At the start of the year, the model advances construction projects that have reached their scheduled commissioning date and constructs available generation and boundary-exchange inputs. The selected dispatch module then calculates operation for that year. At year end, the investment rules use these results to propose additions and retirements, with development times and planning success applied to new projects.

```text
Read the initial fleet, construction pipeline, demand, weather,
    technology costs and study parameters
for each model year:
    Advance the construction pipeline and update the operating fleet
    Construct interval demand, available generation and boundary inputs
    Run the selected annual dispatch method
    Calculate annual revenue, costs and capacity-expansion limits
    Determine investment and retirement decisions
    Update the following year's fleet and construction pipeline
Return annual operating results and asset fleets
```

Dispatch methods connect to investment through common input and annual-output structures. The current staged market, the R029 national research algorithm, national joint clearing, and perfect-foresight linear programming each specify their own bidding, storage-dispatch and cost calculations. Chapters 4–6 describe annual markets and investment, Chapter 7 describes transmission constraints, and Chapter 8 describes perfect-foresight dispatch and hydrology.

## Data and research configurations

The research inputs comprise demand, weather, initial assets, techno-economic parameters, construction projects and boundary exchange. Chapter 2 describes the contents, time coverage and units of the input files. Chapter 3 describes the conversion from weather to available generation. Relevant dataset names and implementation functions follow the corresponding calculation, connecting input processing to the mathematical assumptions.

The R029 national study uses the calendar-corrected data package and its associated annual investment rules. Zonal studies use their regional mappings and boundary inputs. Each chapter states the initial conditions and parameters for the relevant research configuration. Teaching examples use synthetic data distributed with the software.
