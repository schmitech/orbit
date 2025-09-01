defmodule Orbit.MixProject do
  use Mix.Project

  def project do
    [
      app: :orbit_client,
      version: "0.1.0",
      elixir: "~> 1.14",
      start_permanent: Mix.env() == :prod,
      deps: deps()
    ]
  end

  def application do
    [extra_applications: [:logger]]
  end

  defp deps do
    [
      {:mint, "~> 1.5"},
      {:castore, "~> 1.0"},
      {:jason, "~> 1.4"}
    ]
  end
end

