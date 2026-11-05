import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

np.random.seed(67)

time_steps = np.arange(0, 200)
base_signal = 50 + 5 * np.sin(time_steps /  10)

noise = np.random.normal(0, 1.2, size=len(time_steps))
channel_data = base_signal + noise

channel_data[45] = 72.5
channel_data[120] = 25.1
channel_data[175] = 69.8

df_sensor = pd.DataFrame(
    {"Time": time_steps, "Sensor_Channel_1": channel_data}
)

print(df_sensor.head())

x = df_sensor["Sensor_Channel_1"]
mu = x.mean()
sigma = x.std(ddof=0)
z = (x - mu)/sigma

df_sensor["z"] = z
df_sensor["flag"] = z.abs() > 3

print(f"mu =  {mu}")
print(f"sigma = {sigma}")
print(df_sensor.loc[df_sensor["flag"], ["Time", "Sensor_Channel_1", "z"]])

plt.figure()
plt.plot(df_sensor["Time"], x, label="channel")
plt.scatter(
    df_sensor.loc[df_sensor["flag"], "Time"],
    df_sensor.loc[df_sensor["flag"], "Sensor_Channel_1"],
    color="red",
    label="|z|>3",
)
plt.xlabel("Time")
plt.ylabel("Sensor")
plt.title("Synthetic channel (not mission data)")
plt.legend()
plt.show()
