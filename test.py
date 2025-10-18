import xarray as xr
import matplotlib.pyplot as plt


ori_data_path = r"data\grid\wind_velocity.hourly\2020\CARAS.2020010200.wind_velocity.hourly.nc"
cor_data_path = r"output\correction\wind_velocity.hourly\2020\corrected.CARAS.2020010200.wind_velocity.hourly.nc"

ori_data = xr.open_dataset(ori_data_path)
cor_data = xr.open_dataset(cor_data_path)

# 可视化订正前后的nc图
fig, ax = plt.subplots(1, 2, figsize=(12, 6))
ori_data.wind_velocity.plot(ax=ax[0])
ax[0].set_title('Original Data')
cor_data.wind_velocity.plot(ax=ax[1])
ax[1].set_title('Corrected Data')
plt.show()